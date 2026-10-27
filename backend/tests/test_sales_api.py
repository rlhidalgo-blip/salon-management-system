"""Fast transactional API tests; real PostgreSQL locking lives in opt-in tests."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.router import router
from app.modules.transactions.options_router import router as options_router
from app.modules.users.models import User


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def _sqlite_btrim(connection, _record):
        # Ensure a real outer BEGIN precedes SAVEPOINT so failed sales roll back.
        connection.isolation_level = None
        connection.create_function("BTRIM", 1, lambda value: value.strip() if value is not None else None, deterministic=True)
    @event.listens_for(engine, "begin")
    def _sqlite_begin(connection):
        connection.exec_driver_sql("BEGIN")
    for model in (User, Staff, CommissionRule, Service, Product, Transaction, TransactionItem,
                  SaleIdempotency, AuditEvent):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as session:
        session.add_all([User(id=1, username="test_owner", password_hash="synthetic", role="Owner"),
                         User(id=2, username="test_cashier", password_hash="synthetic", role="Cashier"),
                         Staff(id=1, name="Stylist", role="Stylist"),
                         CommissionRule(id=1, name="Percent", type="Percentage", value=Decimal("50.00")),
                         CommissionRule(id=2, name="Fixed", type="Fixed", value=Decimal("25.50"))])
        session.add_all([Service(id=1, name="Cut", current_price=Decimal("101.00"), commission_rule_id=1),
                         Service(id=2, name="Color", current_price=Decimal("100.00"),
                                 allows_variable_price=True, commission_rule_id=1),
                         Product(id=1, name="Oil", current_price=Decimal("100.25"), commission_rule_id=2)])
    import app.modules.transactions.service as service
    import app.modules.transactions.manual_service as manual_service
    monkeypatch.setattr(service, "_database_time", lambda _session: datetime(2026, 10, 22, 16, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "lock_sale_key", lambda *_args: None)
    monkeypatch.setattr(service, "try_lock_sale_key", lambda *_args: True)
    monkeypatch.setattr(manual_service, "_database_time", lambda _session: datetime(2026, 10, 22, 16, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(manual_service, "lock_sale_key", lambda *_args: None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(options_router)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "test_owner", "Owner", "synthetic")
    try:
        with TestClient(app) as client:
            yield client, factory, app
    finally:
        engine.dispose()


def _send(client, payload, key=None):
    return client.post("/api/v1/transactions", json=payload,
                       headers={"Idempotency-Key": str(key or uuid4())})


def _payload():
    return {"payment_method": "GCash", "gcash_reference": "  synthetic-ref  ", "items": [
        {"service_id": 1, "staff_id": 1, "selling_price": "101.00"},
        {"product_id": 1, "staff_id": 1, "selling_price": "100.25"},
        {"product_id": 1, "selling_price": "100.25"},
    ]}


def test_sale_snapshots_totals_and_idempotent_replay(api):
    client, factory, _app = api
    key = uuid4()
    first = _send(client, _payload(), key)
    assert first.status_code == 201, first.json()
    body = first.json()
    assert body["business_date"] == "2026-10-23"
    assert body["gcash_reference"] == "synthetic-ref"
    assert "entry_source" not in body
    assert [item["staff_commission"] for item in body["items"]] == ["51.00", "26.00", "0.00"]
    assert [item["business_share"] for item in body["items"]] == ["50.00", "74.25", "100.25"]
    assert body["gross_sales"] == "301.50"
    assert body["total_staff_commission"] == "77.00"
    assert body["total_business_share"] == "224.50"
    retry = _send(client, _payload(), key)
    assert retry.status_code == 200
    # SQLite drops timezone info; PostgreSQL's TIMESTAMPTZ preserves it.
    assert {k: v for k, v in retry.json().items() if k != "date_time"} == {
        k: v for k, v in body.items() if k != "date_time"}
    changed = _payload()
    changed["items"].pop()
    assert _send(client, changed, key).status_code == 409
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        assert session.scalar(select(func.count()).select_from(TransactionItem)) == 3
        assert session.scalar(select(func.count()).select_from(SaleIdempotency)) == 1


def test_failed_sale_rolls_back_all_writes(api):
    client, factory, _app = api
    payload = _payload()
    payload["items"][1]["selling_price"] = "99.00"
    response = _send(client, payload)
    assert response.status_code == 422
    with factory() as session:
        for model in (Transaction, TransactionItem, SaleIdempotency):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_cashier_can_record_and_missing_auth_is_rejected(api):
    client, _factory, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    assert _send(client, {"payment_method": "Cash", "items": [
        {"service_id": 2, "staff_id": 1, "selling_price": "100.50"}]}).status_code == 201
    del app.dependency_overrides[get_current_principal]
    assert _send(client, _payload()).status_code == 401


def test_cashier_financial_sale_and_previous_day_exact_key_recovery(api, monkeypatch):
    client, _factory, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    key = uuid4()
    recorded = _send(client, _payload(), key)
    assert recorded.status_code == 201
    assert recorded.json()["total_staff_commission"] == "77.00"
    assert recorded.json()["total_business_share"] == "224.50"
    assert recorded.json()["items"][0]["commission_type_snapshot"] == "Percentage"
    import app.modules.transactions.service as service
    monkeypatch.setattr(service, "_database_time",
                        lambda _session: datetime(2026, 10, 24, 16, 30, tzinfo=timezone.utc))
    recovery = client.get(f"/api/v1/transactions/by-idempotency-key/{key}")
    assert recovery.status_code == 200
    assert recovery.json()["status"] == "committed"
    assert recovery.json()["sale"]["id"] == recorded.json()["id"]
    assert recovery.json()["sale"]["total_staff_commission"] == "77.00"
    assert recovery.json()["sale"]["total_business_share"] == "224.50"


@pytest.mark.parametrize("change", [
    {"items": []},
    {"payment_method": "Cash", "gcash_reference": "x"},
    {"items": [{"service_id": 1, "staff_id": 1, "selling_price": "100.00"}]},
    {"items": [{"service_id": 999, "staff_id": 1, "selling_price": "101.00"}]},
])
def test_invalid_sales(api, change):
    client, factory, _app = api
    assert _send(client, {**_payload(), **change}).status_code in (404, 422)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 0


def test_idempotency_header_required_and_uuid(api):
    client, _factory, _app = api
    assert client.post("/api/v1/transactions", json=_payload()).status_code == 422
    assert client.post("/api/v1/transactions", json=_payload(),
                       headers={"Idempotency-Key": "not-a-uuid"}).status_code == 422


def test_unavailable_assignment_and_rounding_edge_fail_closed(api):
    client, factory, _app = api
    with factory.begin() as session:
        session.get(Staff, 1).active = False
    assert _send(client, {"payment_method": "Cash", "items": [
        {"service_id": 1, "staff_id": 1, "selling_price": "101.00"}]}).status_code == 409
    with factory.begin() as session:
        session.get(Staff, 1).active = True
        session.get(CommissionRule, 1).active = False
    assert _send(client, {"payment_method": "Cash", "items": [
        {"service_id": 1, "staff_id": 1, "selling_price": "101.00"}]}).status_code == 409
    with factory.begin() as session:
        session.get(CommissionRule, 1).active = True
        session.get(Product, 1).active = False
    assert _send(client, {"payment_method": "Cash", "items": [
        {"product_id": 1, "selling_price": "100.25"}]}).status_code == 409
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SaleIdempotency)) == 0


def test_same_key_is_scoped_to_authenticated_user(api):
    client, factory, app = api
    key = uuid4()
    first = _send(client, {"payment_method": "Cash", "items": [
        {"product_id": 1, "selling_price": "100.25"}]}, key)
    assert first.status_code == 201
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    second = _send(client, {"payment_method": "Cash", "items": [
        {"product_id": 1, "selling_price": "100.25"}]}, key)
    assert second.status_code == 201 and second.json()["id"] != first.json()["id"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SaleIdempotency)) == 2


def test_whole_peso_rounding_cannot_make_negative_business_share(api):
    client, factory, _app = api
    with factory.begin() as session:
        session.get(CommissionRule, 1).value = Decimal("100.00")
    response = _send(client, {"payment_method": "Cash", "items": [
        {"service_id": 2, "staff_id": 1, "selling_price": "0.75"}]})
    assert response.status_code == 422
    with factory() as session:
        for model in (Transaction, TransactionItem, SaleIdempotency):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_sale_options_are_active_and_do_not_expose_rule_configuration(api):
    client, factory, app = api
    with factory.begin() as session:
        session.get(Staff, 1).active = False
        session.get(Product, 1).active = False
    response = client.get("/api/v1/sales/options")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"staff": [], "services": [
        {"id": 1, "name": "Cut", "current_price": "101.00", "allows_variable_price": False},
        {"id": 2, "name": "Color", "current_price": "100.00", "allows_variable_price": True},
    ], "products": []}
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    assert client.get("/api/v1/sales/options").status_code == 200
    del app.dependency_overrides[get_current_principal]
    assert client.get("/api/v1/sales/options").status_code == 401


def test_sale_options_exclude_inactive_catalog_and_rules(api):
    client, factory, _app = api
    with factory.begin() as session:
        session.get(Service, 1).active = False
        session.get(CommissionRule, 2).active = False
    options = client.get("/api/v1/sales/options")
    assert options.status_code == 200
    assert [row["id"] for row in options.json()["services"]] == [2]
    assert options.json()["products"] == []


def test_manual_options_include_inactive_records_without_financial_configuration(api):
    client, factory, app = api
    with factory.begin() as session:
        session.get(Staff, 1).active = False
        session.get(Service, 2).active = False
        session.get(Product, 1).active = False
    expected = {
        "staff": [{"id": 1, "name": "Stylist", "role": "Stylist", "active": False}],
        "services": [
            {"id": 1, "name": "Cut", "active": True},
            {"id": 2, "name": "Color", "active": False},
        ],
        "products": [{"id": 1, "name": "Oil", "active": False}],
    }
    for principal in (Principal(1, "test_owner", "Owner", "synthetic"),
                      Principal(2, "test_cashier", "Cashier", "synthetic")):
        app.dependency_overrides[get_current_principal] = lambda: principal
        response = client.get("/api/v1/sales/manual-options")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == expected
    direct = client.get("/api/v1/sales/options")
    assert direct.status_code == 200
    assert [row["id"] for row in direct.json()["services"]] == [1]
    assert direct.json()["staff"] == direct.json()["products"] == []
    with factory() as session:
        assert session.get(Staff, 1).active is False
        assert session.get(Service, 2).active is False
        assert session.get(Product, 1).active is False
        assert session.scalar(select(func.count()).select_from(Transaction)) == 0
    del app.dependency_overrides[get_current_principal]
    assert client.get("/api/v1/sales/manual-options").status_code == 401


def test_sale_key_lookup_states_scope_and_validation(api, monkeypatch):
    client, _factory, app = api
    key = uuid4()
    url = f"/api/v1/transactions/by-idempotency-key/{key}"
    absent = client.get(url)
    assert absent.status_code == 200
    assert absent.json() == {"status": "not_committed_at_check", "sale": None}
    assert absent.headers["cache-control"] == "no-store"
    import app.modules.transactions.service as service
    monkeypatch.setattr(service, "try_lock_sale_key", lambda *_args: False)
    processing = client.get(url)
    assert processing.status_code == 202
    assert processing.json() == {"status": "processing", "sale": None}
    monkeypatch.setattr(service, "try_lock_sale_key", lambda *_args: True)
    sale = _send(client, _payload(), key)
    assert sale.status_code == 201
    committed = client.get(url)
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert committed.json()["sale"]["id"] == sale.json()["id"]
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    assert client.get(url).json() == {"status": "not_committed_at_check", "sale": None}
    assert client.get("/api/v1/transactions/by-idempotency-key/not-a-uuid").status_code == 422
    del app.dependency_overrides[get_current_principal]
    assert client.get(url).status_code == 401


def _manual_payload():
    return {"date_time": "2026-10-23T00:15:00+08:00", "manual_reference": " paper-20261023-001 ",
            "verified_against_paper": True, "payment_method": "Cash", "items": [
                {"service_id": 1, "staff_id": 1, "item_name_snapshot": " Old Cut ",
                 "selling_price": "80.25", "commission_type_snapshot": "Percentage",
                 "commission_value_snapshot": "40.00"},
            ]}


def _send_manual(client, payload, key=None):
    return client.post("/api/v1/transactions/manual", json=payload,
                       headers={"Idempotency-Key": str(key or uuid4())})


def test_manual_sale_normalizes_reference_preserves_history_and_replays(api):
    client, factory, _app = api
    key = uuid4()
    first = _send_manual(client, _manual_payload(), key)
    assert first.status_code == 201, first.json()
    body = first.json()
    assert body["business_date"] == "2026-10-23"
    assert body["items"][0]["item_name_snapshot"] == "Old Cut"
    assert body["items"][0]["staff_commission"] == "32.00"
    assert body["items"][0]["business_share"] == "48.25"
    with factory() as session:
        sale = session.get(Transaction, body["id"])
        assert sale.entry_source == "Manual"
        assert sale.manual_reference == "PAPER-20261023-001"
        event_row = session.scalar(select(AuditEvent).where(AuditEvent.resource_id == str(sale.id)))
        assert event_row.actor_user_id == 1
        assert event_row.event_metadata == {"manual_reference": "PAPER-20261023-001",
                                          "business_date": "2026-10-23"}
    replay = _send_manual(client, {**_manual_payload(), "manual_reference": "PAPER-20261023-001"}, key)
    assert replay.status_code == 200 and replay.json()["id"] == body["id"]
    assert _send_manual(client, {**_manual_payload(), "items": [
        {**_manual_payload()["items"][0], "selling_price": "81.00"}]}, key).status_code == 409
    assert _send_manual(client, _manual_payload()).status_code == 409
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1
        assert session.scalar(select(func.count()).select_from(SaleIdempotency)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_manual_cashier_same_day_and_owner_previous_day(api, monkeypatch):
    client, factory, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    assert _send_manual(client, _manual_payload()).status_code == 201
    previous = {**_manual_payload(), "date_time": "2026-10-22T14:00:00+08:00",
                "manual_reference": "PAPER-20261022-001"}
    assert _send_manual(client, previous).status_code == 403
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "test_owner", "Owner", "synthetic")
    assert _send_manual(client, previous).status_code == 201
    import app.modules.transactions.manual_service as manual_service
    monkeypatch.setattr(manual_service, "_database_time",
                        lambda _session: datetime(2026, 10, 23, 16, 30, tzinfo=timezone.utc))
    assert _send_manual(client, {**_manual_payload(), "manual_reference": "PAPER-20261023-002"}).status_code == 201
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 3


@pytest.mark.parametrize("change,status", [
    ({"verified_against_paper": False}, 422),
    ({"verified_against_paper": "true"}, 422),
    ({"manual_reference": "PAPER-20261023-000"}, 422),
    ({"manual_reference": "PAPER-20261023-1000"}, 422),
    ({"manual_reference": "PAPER-20260230-001"}, 422),
    ({"manual_reference": "PAPER-20261022-001"}, 422),
    ({"date_time": "2026-10-23T01:00:00+08:00"}, 422),
    ({"date_time": "2026-10-23T00:15:00"}, 422),
    ({"payment_method": "GCash"}, 422),
    ({"payment_method": "Cash", "gcash_reference": "x"}, 422),
    ({"items": [{"service_id": 999, "staff_id": 1, "item_name_snapshot": "Old Cut",
                "selling_price": "80.25", "commission_type_snapshot": "Percentage",
                "commission_value_snapshot": "40.00"}]}, 404),
    ({"items": [{"service_id": 1, "staff_id": 999, "item_name_snapshot": "Old Cut",
                "selling_price": "80.25", "commission_type_snapshot": "Percentage",
                "commission_value_snapshot": "40.00"}]}, 404),
    ({"items": [{"service_id": 1, "staff_id": 1, "item_name_snapshot": "Old Cut",
                "selling_price": "80.25", "commission_type_snapshot": "Fixed",
                "commission_value_snapshot": "40.00"}]}, 422),
    ({"items": [{"service_id": 1, "staff_id": 1, "item_name_snapshot": "Old Cut",
                "selling_price": "0.50", "commission_type_snapshot": "Percentage",
                "commission_value_snapshot": "100.00"}]}, 422),
])
def test_invalid_manual_sale_rolls_back(api, change, status):
    client, factory, _app = api
    assert _send_manual(client, {**_manual_payload(), **change}).status_code == status
    with factory() as session:
        for model in (Transaction, TransactionItem, SaleIdempotency, AuditEvent):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_manual_inactive_references_and_voided_reference_conflict(api):
    client, factory, _app = api
    with factory.begin() as session:
        session.get(Staff, 1).active = False
        session.get(Service, 1).active = False
        session.get(CommissionRule, 1).active = False
    first = _send_manual(client, _manual_payload())
    assert first.status_code == 201, first.json()
    with factory.begin() as session:
        sale = session.get(Transaction, first.json()["id"])
        sale.status = "Voided"
        sale.void_reason = "synthetic test void"
        sale.voided_by_user_id = 1
        sale.voided_at = datetime(2026, 10, 22, 16, 30, tzinfo=timezone.utc)
    assert _send_manual(client, _manual_payload()).status_code == 409


def test_manual_cashier_midnight_during_unique_wait_rolls_back(api, monkeypatch):
    client, factory, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "test_cashier", "Cashier", "synthetic")
    import app.modules.transactions.manual_service as manual_service
    clock = iter((datetime(2026, 10, 23, 15, 59, tzinfo=timezone.utc),
                  datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)))
    monkeypatch.setattr(manual_service, "_database_time", lambda _session: next(clock))
    assert _send_manual(client, _manual_payload()).status_code == 403
    with factory() as session:
        for model in (Transaction, TransactionItem, SaleIdempotency, AuditEvent):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_manual_one_item_per_unit_and_product_commissions(api):
    client, factory, _app = api
    base = _manual_payload()
    with_staff = {"product_id": 1, "staff_id": 1, "item_name_snapshot": "Old Oil",
                  "selling_price": "80.25", "commission_type_snapshot": "Fixed",
                  "commission_value_snapshot": "25.50"}
    without_staff = {"product_id": 1, "item_name_snapshot": "Old Oil",
                     "selling_price": "80.25"}
    response = _send_manual(client, {**base, "items": [base["items"][0], base["items"][0],
                                                       with_staff, without_staff]})
    assert response.status_code == 201, response.json()
    assert [item["staff_commission"] for item in response.json()["items"]] == [
        "32.00", "32.00", "26.00", "0.00"]
    assert response.json()["gross_sales"] == "321.00"
    assert response.json()["total_staff_commission"] == "90.00"
    assert response.json()["total_business_share"] == "231.00"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TransactionItem)) == 4
