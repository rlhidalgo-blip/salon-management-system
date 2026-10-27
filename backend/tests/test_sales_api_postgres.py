"""Opt-in, rollback-only PostgreSQL sale checks on yabs_salon_test.

Savepoint-backed commits do not prove cross-connection durability or the
two-connection same-key race; both remain required before production use.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

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
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


ORIGIN = "http://localhost"
MODELS = (User, AuthSession, CommissionRule, Service, Product, Staff,
          Transaction, TransactionItem, SaleIdempotency, AuditEvent)


@pytest.fixture
def db_api(monkeypatch):
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for isolated PostgreSQL tests")
    url = get_database_url()
    if url.database != "yabs_salon_test" or url.host not in ("localhost", "127.0.0.1") or url.username != "yabs_app":
        pytest.fail("Target must be local yabs_salon_test using yabs_app; no writes attempted")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Connected database is not yabs_salon_test; no writes attempted")
            if connection.scalar(text("SELECT current_user")) != "yabs_app":
                pytest.fail("Connected user is not yabs_app; no writes attempted")
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                pytest.fail("Missing Alembic revision; no writes attempted")
            if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01":
                pytest.fail("Unexpected Alembic revision; no writes attempted")
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in MODELS}
            connection.rollback()
            outer = connection.begin()
            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-sales-test-secret-not-for-deployment-123")

            def session_override():
                with Session(bind=connection, autoflush=False, expire_on_commit=False,
                             join_transaction_mode="create_savepoint") as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            marker = f"synthetic-sale-{uuid4().hex}"
            try:
                with TestClient(app, base_url=ORIGIN) as client:
                    yield connection, client, marker
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                if not outer.is_active:
                    pytest.fail("Outer rollback safety was lost")
                outer.rollback()
        with engine.connect() as verifier:
            assert verifier.scalar(text("SELECT current_database()")) == "yabs_salon_test"
            for model in MODELS:
                assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
            assert verifier.scalar(select(func.count()).select_from(User).where(User.username.like(marker + "%"))) == 0
    finally:
        engine.dispose()


def _seed(connection, marker):
    password = "synthetic-test-password-not-real"
    user_id = connection.execute(insert(User).values(
        username=marker + "-owner", password_hash=hash_password(password), role="Owner", active=True,
    ).returning(User.id)).scalar_one()
    staff_id = connection.execute(insert(Staff).values(name=marker + "-staff", role="Stylist")
                                  .returning(Staff.id)).scalar_one()
    rule_id = connection.execute(insert(CommissionRule).values(
        name=marker + "-rule", type="Percentage", value=Decimal("50.00"), active=True,
    ).returning(CommissionRule.id)).scalar_one()
    service_id = connection.execute(insert(Service).values(
        name=marker + "-service", current_price=Decimal("101.00"),
        commission_rule_id=rule_id, active=True,
    ).returning(Service.id)).scalar_one()
    return password, user_id, staff_id, rule_id, service_id


def test_manual_options_owner_cashier_and_direct_options_regression(db_api):
    connection, client, marker = db_api
    password, _user_id, staff_id, rule_id, service_id = _seed(connection, marker)
    inactive_staff_id = connection.execute(insert(Staff).values(
        name=marker + "-inactive-staff", role="Barber", active=False,
    ).returning(Staff.id)).scalar_one()
    inactive_service_id = connection.execute(insert(Service).values(
        name=marker + "-inactive-service", current_price=Decimal("99.00"),
        commission_rule_id=rule_id, active=False,
    ).returning(Service.id)).scalar_one()
    fixed_rule_id = connection.execute(insert(CommissionRule).values(
        name=marker + "-fixed", type="Fixed", value=Decimal("10.00"), active=True,
    ).returning(CommissionRule.id)).scalar_one()
    product_id = connection.execute(insert(Product).values(
        name=marker + "-product", current_price=Decimal("20.00"),
        commission_rule_id=fixed_rule_id, active=False,
    ).returning(Product.id)).scalar_one()
    connection.execute(insert(User).values(
        username=marker + "-cashier", password_hash=hash_password(password), role="Cashier", active=True,
    ))
    url = "/api/v1/sales/manual-options"
    assert client.get(url).status_code == 401
    before = {model: connection.scalar(select(func.count()).select_from(model))
              for model in (Staff, Service, Product, CommissionRule, Transaction)}
    for role in ("owner", "cashier"):
        login = client.post("/api/v1/auth/login", json={
            "username": marker + "-" + role, "password": password,
        }, headers={"Origin": ORIGIN})
        assert login.status_code == 200
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert [row for row in body["staff"] if row["id"] in (staff_id, inactive_staff_id)] == [
            {"id": staff_id, "name": marker + "-staff", "role": "Stylist", "active": True},
            {"id": inactive_staff_id, "name": marker + "-inactive-staff", "role": "Barber", "active": False},
        ]
        assert [row for row in body["services"] if row["id"] in (service_id, inactive_service_id)] == [
            {"id": service_id, "name": marker + "-service", "active": True},
            {"id": inactive_service_id, "name": marker + "-inactive-service", "active": False},
        ]
        assert [row for row in body["products"] if row["id"] == product_id] == [
            {"id": product_id, "name": marker + "-product", "active": False},
        ]
        direct = client.get("/api/v1/sales/options")
        assert direct.status_code == 200
        assert service_id in [row["id"] for row in direct.json()["services"]]
        assert inactive_service_id not in [row["id"] for row in direct.json()["services"]]
        assert product_id not in [row["id"] for row in direct.json()["products"]]
    for model, count in before.items():
        assert connection.scalar(select(func.count()).select_from(model)) == count


def test_real_constraints_auth_idempotency_and_rollback(db_api):
    connection, client, marker = db_api
    password, user_id, staff_id, rule_id, service_id = _seed(connection, marker)
    login = client.post("/api/v1/auth/login", json={"username": marker + "-owner", "password": password},
                        headers={"Origin": ORIGIN})
    assert login.status_code == 200
    headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"],
               "Idempotency-Key": str(uuid4())}
    payload = {"payment_method": "Cash", "items": [
        {"service_id": service_id, "staff_id": staff_id, "selling_price": "101.00"},
        {"service_id": service_id, "staff_id": staff_id, "selling_price": "101.00"},
    ]}
    assert client.post("/api/v1/transactions", json=payload,
                       headers={"Origin": ORIGIN, "Idempotency-Key": headers["Idempotency-Key"]}).status_code == 403
    first = client.post("/api/v1/transactions", json=payload, headers=headers)
    assert first.status_code == 201, first.json()
    assert first.json()["total_staff_commission"] == "102.00"  # 51 + 51, not aggregate rounding.
    assert first.json()["total_business_share"] == "100.00"
    transaction_id = first.json()["id"]
    assert connection.scalar(select(Transaction.entry_source).where(Transaction.id == transaction_id)) == "Direct"
    assert connection.scalar(select(func.count()).select_from(TransactionItem).where(
        TransactionItem.transaction_id == transaction_id)) == 2
    replay = client.post("/api/v1/transactions", json=payload, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    changed = {**payload, "items": payload["items"][:1]}
    assert client.post("/api/v1/transactions", json=changed, headers=headers).status_code == 409
    assert connection.scalar(select(func.count()).select_from(SaleIdempotency).where(
        SaleIdempotency.user_id == user_id)) == 1

    bad_headers = {**headers, "Idempotency-Key": str(uuid4())}
    bad_payload = {**payload, "items": [
        payload["items"][0], {"service_id": service_id, "staff_id": staff_id, "selling_price": "100.00"},
    ]}
    assert client.post("/api/v1/transactions", json=bad_payload, headers=bad_headers).status_code == 422
    assert connection.scalar(select(func.count()).select_from(SaleIdempotency).where(
        SaleIdempotency.idempotency_key == bad_headers["Idempotency-Key"])) == 0
    assert connection.scalar(select(func.count()).select_from(Transaction)) >= 1
    # Historical snapshots remain after a current catalog change in the same isolated transaction.
    connection.execute(Service.__table__.update().where(Service.id == service_id).values(
        name=marker + "-renamed", current_price=Decimal("120.00")))
    assert connection.scalar(select(TransactionItem.item_name_snapshot).where(
        TransactionItem.transaction_id == transaction_id).limit(1)) == marker + "-service"


def _free_paper_reference(connection, business_date):
    for number in range(1, 1000):
        candidate = f"PAPER-{business_date:%Y%m%d}-{number:03d}"
        if connection.scalar(select(Transaction.id).where(Transaction.manual_reference == candidate)) is None:
            return candidate
    pytest.fail("No unused paper references for the isolated test date; no manual sale written")


def test_manual_sale_constraints_audit_reports_and_rollback(db_api):
    connection, client, marker = db_api
    password, user_id, staff_id, _rule_id, service_id = _seed(connection, marker)
    # These synthetic records existed for the paper sale but are inactive now.
    connection.execute(Staff.__table__.update().where(Staff.id == staff_id).values(active=False))
    connection.execute(Service.__table__.update().where(Service.id == service_id).values(active=False))
    connection.execute(CommissionRule.__table__.update().where(CommissionRule.id == _rule_id).values(active=False))
    cashier_id = connection.execute(insert(User).values(
        username=marker + "-cashier", password_hash=hash_password(password), role="Cashier", active=True,
    ).returning(User.id)).scalar_one()
    login = client.post("/api/v1/auth/login", json={"username": marker + "-owner", "password": password},
                        headers={"Origin": ORIGIN})
    assert login.status_code == 200
    now = connection.scalar(select(func.clock_timestamp()))
    manila = ZoneInfo("Asia/Manila")
    today = now.astimezone(manila).date()
    previous = today - timedelta(days=1)
    original = datetime.combine(previous, datetime.min.time(), manila) + timedelta(hours=14)
    reference = _free_paper_reference(connection, previous)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"],
               "Idempotency-Key": str(uuid4())}
    payload = {"date_time": original.isoformat(), "manual_reference": " " + reference.lower() + " ",
               "verified_against_paper": True, "payment_method": "GCash",
               "gcash_reference": "synthetic-test-payment", "items": [
                   {"service_id": service_id, "staff_id": staff_id,
                    "item_name_snapshot": marker + "-original-name", "selling_price": "80.25",
                    "commission_type_snapshot": "Percentage", "commission_value_snapshot": "40.00"},
               ]}
    endpoint = "/api/v1/transactions/manual"
    assert client.post(endpoint, json=payload, headers={**headers, "X-CSRF-Token": "wrong"}).status_code == 403
    before = client.get(f"/api/v1/reports/daily?business_date={previous.isoformat()}").json()
    month = previous.strftime("%Y-%m")
    monthly_before = client.get(f"/api/v1/reports/monthly?month={month}")
    assert monthly_before.status_code == 200
    first = client.post(endpoint, json=payload, headers=headers)
    assert first.status_code == 201, first.json()
    sale_id = first.json()["id"]
    assert first.json()["business_date"] == previous.isoformat()
    assert first.json()["total_staff_commission"] == "32.00"
    assert first.json()["total_business_share"] == "48.25"
    assert connection.scalar(select(Transaction.manual_reference).where(Transaction.id == sale_id)) == reference
    assert connection.scalar(select(Transaction.entry_source).where(Transaction.id == sale_id)) == "Manual"
    assert connection.scalar(select(TransactionItem.item_name_snapshot).where(
        TransactionItem.transaction_id == sale_id)) == marker + "-original-name"
    assert connection.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.resource_id == str(sale_id), AuditEvent.event_type == "ManualSaleCreated")) == 1
    after = client.get(f"/api/v1/reports/daily?business_date={previous.isoformat()}").json()
    assert Decimal(after["gross_sales"]) - Decimal(before["gross_sales"]) == Decimal("80.25")
    assert Decimal(after["total_staff_commission"]) - Decimal(before["total_staff_commission"]) == Decimal("32.00")
    monthly = client.get(f"/api/v1/reports/monthly?month={month}")
    assert monthly.status_code == 200
    assert Decimal(monthly.json()["gross_sales"]) - Decimal(monthly_before.json()["gross_sales"]) == Decimal("80.25")
    assert (Decimal(monthly.json()["total_staff_commission"])
            - Decimal(monthly_before.json()["total_staff_commission"])) == Decimal("32.00")
    replay = client.post(endpoint, json={**payload, "manual_reference": reference}, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == sale_id
    another = client.post(endpoint, json=payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert another.status_code == 409
    assert connection.scalar(select(func.count()).select_from(SaleIdempotency).where(
        SaleIdempotency.transaction_id == sale_id)) == 1
    invalid = {**payload, "manual_reference": _free_paper_reference(connection, previous),
               "items": [{**payload["items"][0], "selling_price": "0.50",
                          "commission_value_snapshot": "100.00"}]}
    assert client.post(endpoint, json=invalid, headers={**headers, "Idempotency-Key": str(uuid4())}).status_code == 422
    assert connection.scalar(select(func.count()).select_from(Transaction).where(
        Transaction.manual_reference == invalid["manual_reference"])) == 0
    assert connection.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.resource_id == str(sale_id), AuditEvent.event_type == "ManualSaleCreated")) == 1
    voided = client.post(f"/api/v1/transactions/{sale_id}/void", json={"reason": "synthetic correction"},
                         headers={"Origin": ORIGIN, "X-CSRF-Token": headers["X-CSRF-Token"]})
    assert voided.status_code == 200
    assert client.post(endpoint, json=payload, headers={**headers, "Idempotency-Key": str(uuid4())}).status_code == 409
    assert connection.scalar(select(Transaction.manual_reference).where(Transaction.id == sale_id)) == reference
    # Exercise the same endpoint under a real Cashier session; prior-day is forbidden.
    cashier_login = client.post("/api/v1/auth/login", json={"username": marker + "-cashier", "password": password},
                                headers={"Origin": ORIGIN})
    assert cashier_login.status_code == 200
    cashier_headers = {"Origin": ORIGIN, "X-CSRF-Token": cashier_login.json()["csrf_token"],
                       "Idempotency-Key": str(uuid4())}
    assert client.post(endpoint, json={**payload, "manual_reference": _free_paper_reference(connection, previous)},
                       headers=cashier_headers).status_code == 403
    assert connection.scalar(select(func.count()).select_from(Transaction).where(
        Transaction.recorded_by_user_id == cashier_id)) == 0
