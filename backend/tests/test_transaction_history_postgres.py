"""Opt-in, rollback-only PostgreSQL history/void checks on yabs_salon_test."""

import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from ipaddress import ip_address
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.security import hash_password
from app.db.session import get_db_session
from app.main import app
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.staff.models import Staff
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


ORIGIN = "http://localhost"
MODELS = (User, AuthSession, Staff, CommissionRule, Service, Transaction, TransactionItem, AuditEvent)


def _safe_target(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured PostgreSQL target; no writes attempted")
    if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
        pytest.fail("Unsafe connected database; no writes attempted")
    if connection.scalar(text("SELECT current_user")) != "yabs_app":
        pytest.fail("Unsafe connected user; no writes attempted")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if address is None or not ip_address(str(address)).is_loopback:
        pytest.fail("PostgreSQL is not on loopback; no writes attempted")
    if connection.scalar(text("SELECT current_schema()")) != "public":
        pytest.fail("Unexpected schema; no writes attempted")
    if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
        pytest.fail("Missing Alembic revision; no writes attempted")
    revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
    has_attempts = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
    if (revision, has_attempts) not in (("20261020_01", False), ("20261027_01", True)):
        pytest.fail("Unexpected Alembic revision; no writes attempted")


@pytest.fixture
def db_case(monkeypatch):
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured PostgreSQL target; no writes attempted")
    engine = create_engine(url, connect_args={"connect_timeout": 5,
                                              "options": "-c statement_timeout=15000 -c lock_timeout=10000"})
    marker = "synthetic-history-" + uuid4().hex
    try:
        with engine.connect() as connection:
            _safe_target(connection, url)
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in MODELS}
            connection.rollback()
            outer = connection.begin()
            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", secrets.token_urlsafe(32))
            def session_override():
                with Session(bind=connection, autoflush=False, expire_on_commit=False,
                             join_transaction_mode="create_savepoint") as session:
                    yield session
            app.dependency_overrides[get_db_session] = session_override
            try:
                password = secrets.token_urlsafe(32)
                owner_id = connection.execute(insert(User).values(
                    username=marker + "-owner", password_hash=hash_password(password), role="Owner",
                    active=True).returning(User.id)).scalar_one()
                cashier_id = connection.execute(insert(User).values(
                    username=marker + "-cashier", password_hash=hash_password(password), role="Cashier",
                    active=True).returning(User.id)).scalar_one()
                staff_id = connection.execute(insert(Staff).values(
                    name=marker + "-staff", role="Stylist", active=True).returning(Staff.id)).scalar_one()
                rule_id = connection.execute(insert(CommissionRule).values(
                    name=marker + "-rule", type="Percentage", value=Decimal("50.00"),
                    active=True).returning(CommissionRule.id)).scalar_one()
                service_id = connection.execute(insert(Service).values(
                    name=marker + "-service", current_price=Decimal("101.00"),
                    commission_rule_id=rule_id, active=True).returning(Service.id)).scalar_one()
                occurred = connection.scalar(text("SELECT clock_timestamp()"))
                manila_day = connection.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Manila')::date"))
                transaction_id = connection.execute(insert(Transaction).values(
                    date_time=occurred, business_date=manila_day, recorded_by_user_id=cashier_id,
                    entry_source="Direct", payment_method="GCash", gcash_reference=marker + "-ref",
                    status="Completed").returning(Transaction.id)).scalar_one()
                item_id = connection.execute(insert(TransactionItem).values(
                    transaction_id=transaction_id, service_id=service_id, staff_id=staff_id,
                    item_name_snapshot=marker + "-original", selling_price=Decimal("101.00"),
                    commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                    staff_commission=Decimal("51.00"), business_share=Decimal("50.00")
                ).returning(TransactionItem.id)).scalar_one()
                with TestClient(app, base_url=ORIGIN) as owner_client, TestClient(app, base_url=ORIGIN) as cashier_client:
                    owner_login = owner_client.post("/api/v1/auth/login", json={
                        "username": marker + "-owner", "password": password}, headers={"Origin": ORIGIN})
                    cashier_login = cashier_client.post("/api/v1/auth/login", json={
                        "username": marker + "-cashier", "password": password}, headers={"Origin": ORIGIN})
                    assert owner_login.status_code == cashier_login.status_code == 200
                    yield (connection, owner_client, cashier_client, transaction_id, item_id,
                           {"Origin": ORIGIN, "X-CSRF-Token": owner_login.json()["csrf_token"]},
                           {"Origin": ORIGIN, "X-CSRF-Token": cashier_login.json()["csrf_token"]})
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                if not outer.is_active:
                    pytest.fail("Outer rollback safety was lost")
                outer.rollback()
        with engine.connect() as verifier:
            _safe_target(verifier, url)
            for model in MODELS:
                assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
            assert verifier.scalar(select(func.count()).select_from(User).where(
                User.username.like(marker + "%"))) == 0
    finally:
        engine.dispose()


def test_postgres_history_privacy_and_void_audits(db_case):
    connection, owner, cashier, transaction_id, item_id, owner_headers, cashier_headers = db_case
    owner_list = owner.get("/api/v1/transactions")
    cashier_list = cashier.get("/api/v1/transactions")
    assert owner_list.status_code == cashier_list.status_code == 200
    owner_row = next(row for row in owner_list.json()["items"] if row["id"] == transaction_id)
    cashier_row = next(row for row in cashier_list.json()["items"] if row["id"] == transaction_id)
    assert owner_row["total_staff_commission"] == "51.00"
    assert cashier_row["total_staff_commission"] == "51.00"
    assert cashier_row["total_business_share"] == "50.00"
    assert "gcash_reference" not in cashier_row
    detail = cashier.get(f"/api/v1/transactions/{transaction_id}")
    assert detail.status_code == 200 and detail.json()["gcash_reference"] is not None
    assert detail.json()["items"][0]["commission_type_snapshot"] == "Percentage"
    assert detail.json()["items"][0]["commission_value_snapshot"] == "50.00"
    assert detail.json()["items"][0]["staff_commission"] == "51.00"
    assert detail.json()["items"][0]["business_share"] == "50.00"
    assert "void_reason" not in detail.json()
    assert cashier.get("/api/v1/transactions?business_date=2020-01-01").status_code == 403
    denied = cashier.post(f"/api/v1/transactions/{transaction_id}/void",
                          json={"reason": "synthetic"}, headers=cashier_headers)
    assert denied.status_code == 403
    assert connection.scalar(select(Transaction.status).where(Transaction.id == transaction_id)) == "Completed"
    assert owner.post(f"/api/v1/transactions/{transaction_id}/void",
                      json={"reason": "synthetic mistake"}).status_code == 403
    assert connection.scalar(select(Transaction.status).where(Transaction.id == transaction_id)) == "Completed"
    success = owner.post(f"/api/v1/transactions/{transaction_id}/void",
                         json={"reason": "synthetic mistake"}, headers=owner_headers)
    assert success.status_code == 200, success.json()
    assert success.json()["status"] == "Voided"
    assert owner.post(f"/api/v1/transactions/{transaction_id}/void",
                      json={"reason": "duplicate"}, headers=owner_headers).status_code == 409
    assert connection.scalar(select(TransactionItem.staff_commission).where(
        TransactionItem.id == item_id)) == Decimal("51.00")
    audits = list(connection.execute(select(AuditEvent.outcome).where(
        AuditEvent.event_type == "TransactionVoid", AuditEvent.resource_id == str(transaction_id))
        .order_by(AuditEvent.id)).scalars())
    assert audits == ["Failure", "Success", "Failure"]
