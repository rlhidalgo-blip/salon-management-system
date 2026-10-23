"""Opt-in catalog integration tests, guarded to yabs_salon_test and outer rollback.

Savepoint-backed API commits do not prove durable cross-connection visibility.
"""

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.exc import OperationalError
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
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


ORIGIN = "http://localhost"
PASSWORD = "synthetic-catalog-test-password"
MODELS = (User, AuthSession, AuditEvent, CommissionRule, Service, Product, Staff, Transaction, TransactionItem)


@pytest.fixture
def db_api(monkeypatch):
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL integration tests")
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
                pytest.fail("Alembic revision absent; no writes attempted")
            if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01":
                pytest.fail("Unexpected Alembic revision; no writes attempted")
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in MODELS}
            baseline_rule_id = connection.scalar(select(CommissionRule.id).order_by(CommissionRule.id).limit(1))
            connection.rollback()
            outer = connection.begin()
            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-catalog-test-key-not-a-real-secret-123")

            def session_override():
                with Session(bind=connection, autoflush=False, expire_on_commit=False,
                             join_transaction_mode="create_savepoint") as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            marker = f"catalog-test-{uuid4().hex}"
            try:
                with TestClient(app, base_url=ORIGIN) as client:
                    yield connection, client, marker, engine, baseline_rule_id
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                if not outer.is_active:
                    pytest.fail("Outer transaction ended unexpectedly; rollback safety lost")
                outer.rollback()
        with engine.connect() as verifier:
            assert verifier.scalar(text("SELECT current_database()")) == "yabs_salon_test"
            for model in MODELS:
                assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
            assert verifier.scalar(select(func.count()).select_from(Service).where(Service.name.like(marker + "%"))) == 0
            assert verifier.scalar(select(func.count()).select_from(Product).where(Product.name.like(marker + "%"))) == 0
    finally:
        engine.dispose()


def login(connection, client, marker, role="Owner"):
    username = f"{marker}-{role.lower()}"
    user_id = connection.execute(insert(User).values(
        username=username, password_hash=hash_password(PASSWORD), role=role, active=True,
    ).returning(User.id)).scalar_one()
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD},
                           headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return user_id, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def rules(connection, marker):
    percentage = connection.execute(insert(CommissionRule).values(
        name=marker + "-percentage", type="Percentage", value=Decimal("50"), active=True,
    ).returning(CommissionRule.id)).scalar_one()
    fixed = connection.execute(insert(CommissionRule).values(
        name=marker + "-fixed", type="Fixed", value=Decimal("25"), active=True,
    ).returning(CommissionRule.id)).scalar_one()
    return percentage, fixed


def test_catalog_writes_security_and_history(db_api):
    connection, client, marker, _engine, _baseline_rule_id = db_api
    owner_id, headers = login(connection, client, marker)
    percentage, fixed = rules(connection, marker)
    service_data = {"name": marker + "-service", "current_price": "100.00", "commission_rule_id": percentage}
    product_data = {"name": marker + "-product", "current_price": "100.00", "commission_rule_id": fixed}
    assert client.post("/api/v1/services", json=service_data, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post("/api/v1/services", json=service_data, headers=headers).status_code == 201
    product = client.post("/api/v1/products", json=product_data, headers=headers)
    assert product.status_code == 201
    sid = client.get("/api/v1/services").json()[-1]["id"]
    pid = product.json()["id"]
    assert client.patch(f"/api/v1/products/{pid}", json={"current_price": "24.99"}, headers=headers).status_code == 422
    assert connection.scalar(select(Product.current_price).where(Product.id == pid)) == Decimal("100.00")
    assert client.patch(f"/api/v1/products/{pid}", json={"commission_rule_id": percentage}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/services/{sid}", json={"commission_rule_id": fixed}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/commission-rules/{percentage}/status", json={"active": False}, headers=headers).status_code == 409
    staff_id = connection.execute(insert(Staff).values(name=marker + "-staff", role="Barber").returning(Staff.id)).scalar_one()
    transaction_id = connection.execute(insert(Transaction).values(
        business_date=date(2026, 10, 23), recorded_by_user_id=owner_id,
        entry_source="Direct", payment_method="Cash",
    ).returning(Transaction.id)).scalar_one()
    item_id = connection.execute(insert(TransactionItem).values(
        transaction_id=transaction_id, service_id=sid, staff_id=staff_id,
        item_name_snapshot="Original service", selling_price=Decimal("100.00"),
        commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
        staff_commission=Decimal("50.00"), business_share=Decimal("50.00"),
    ).returning(TransactionItem.id)).scalar_one()
    assert client.patch(f"/api/v1/services/{sid}", json={"name": marker + "-renamed", "current_price": "120.00"},
                        headers=headers).status_code == 200
    assert client.patch(f"/api/v1/services/{sid}/status", json={"active": False}, headers=headers).status_code == 200
    snapshot = connection.execute(select(TransactionItem.item_name_snapshot, TransactionItem.selling_price,
        TransactionItem.commission_value_snapshot, TransactionItem.staff_commission, TransactionItem.business_share)
        .where(TransactionItem.id == item_id)).one()
    assert snapshot == ("Original service", Decimal("100.00"), Decimal("50.00"), Decimal("50.00"), Decimal("50.00"))
    assert client.patch(f"/api/v1/commission-rules/{percentage}/status", json={"active": False}, headers=headers).status_code == 200
    assert client.patch(f"/api/v1/services/{sid}/status", json={"active": True}, headers=headers).status_code == 409
    assert client.patch(f"/api/v1/services/{sid}", json={"commission_rule_id": fixed}, headers=headers).status_code == 422
    cashier_id, cashier_headers = login(connection, client, marker, "Cashier")
    assert cashier_id != owner_id
    assert client.get("/api/v1/services").status_code == 403
    assert client.post("/api/v1/products", json=product_data, headers=cashier_headers).status_code == 403
    assert client.patch(f"/api/v1/products/{pid}/status", json={"active": False}, headers=cashier_headers).status_code == 403


def test_rule_row_lock_is_shared_with_catalog_writes(db_api):
    connection, _client, _marker, engine, baseline_rule_id = db_api
    if baseline_rule_id is None:
        pytest.skip("No pre-existing test rule; rollback-only synthetic rule is invisible to a second connection")
    connection.scalar(select(CommissionRule.id).where(CommissionRule.id == baseline_rule_id).with_for_update())
    with engine.connect() as second:
        assert second.scalar(text("SELECT current_database()")) == "yabs_salon_test"
        try:
            with pytest.raises(OperationalError) as exc:
                second.scalar(select(CommissionRule.id).where(CommissionRule.id == baseline_rule_id)
                              .with_for_update(nowait=True))
            assert exc.value.orig.sqlstate == "55P03"
        finally:
            second.rollback()
