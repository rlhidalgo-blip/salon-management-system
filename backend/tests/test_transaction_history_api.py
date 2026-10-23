"""Fast history/void tests; PostgreSQL locks are covered by guarded tests."""

import base64
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.router import router
from app.modules.users.models import User


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def _begin_explicitly(connection, _record):
        connection.isolation_level = None
        connection.create_function("BTRIM", 1, lambda value: value.strip() if value else value, deterministic=True)
    @event.listens_for(engine, "begin")
    def _begin(connection):
        connection.exec_driver_sql("BEGIN")
    for model in (User, Staff, CommissionRule, Service, Product, Transaction, TransactionItem, AuditEvent):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)
    import app.modules.transactions.history_service as history
    monkeypatch.setattr(history, "_database_time", lambda _session: now)
    with factory.begin() as session:
        session.add_all([
            User(id=1, username="history_owner", password_hash="synthetic", role="Owner"),
            User(id=2, username="history_cashier_a", password_hash="synthetic", role="Cashier"),
            User(id=3, username="history_cashier_b", password_hash="synthetic", role="Cashier"),
            Staff(id=1, name="Synthetic Stylist", role="Stylist"),
            CommissionRule(id=1, name="Synthetic Percent", type="Percentage", value=Decimal("50.00")),
            Service(id=1, name="Current Name", current_price=Decimal("200.00"), commission_rule_id=1),
        ])
        session.add_all([
            Transaction(id=1, date_time=now, business_date=date(2026, 10, 23), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="Cash", status="Completed"),
            Transaction(id=2, date_time=now, business_date=date(2026, 10, 23), recorded_by_user_id=3,
                        entry_source="Direct", payment_method="GCash", gcash_reference="synthetic-ref",
                        status="Completed"),
            Transaction(id=3, date_time=datetime(2026, 10, 21, 17, tzinfo=timezone.utc),
                        business_date=date(2026, 10, 22), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="Cash", status="Completed"),
        ])
        session.add_all([
            TransactionItem(id=1, transaction_id=1, service_id=1, staff_id=1,
                            item_name_snapshot="Original Name", selling_price=Decimal("101.00"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("51.00"), business_share=Decimal("50.00")),
            TransactionItem(id=2, transaction_id=2, service_id=1, staff_id=1,
                            item_name_snapshot="Other Item", selling_price=Decimal("120.00"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("60.00"), business_share=Decimal("60.00")),
            TransactionItem(id=3, transaction_id=3, service_id=1, staff_id=1,
                            item_name_snapshot="Past Item", selling_price=Decimal("90.00"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("45.00"), business_share=Decimal("45.00")),
        ])
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)
    def session_override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "history_owner", "Owner", "synthetic")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory, app, monkeypatch
    finally:
        engine.dispose()


def _cashier(app, user_id=2):
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id, f"history_cashier_{user_id}", "Cashier", "synthetic")


def test_owner_history_stable_bounded_pagination_and_past_date(api):
    client, _factory, _app, _monkeypatch = api
    first = client.get("/api/v1/transactions?limit=1")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert [row["id"] for row in first.json()["items"]] == [1]
    cursor = first.json()["next_cursor"]
    second = client.get("/api/v1/transactions", params={"limit": 1, "cursor": cursor})
    assert second.status_code == 200, second.json()
    assert [row["id"] for row in second.json()["items"]] == [2]
    assert second.json()["next_cursor"] is None
    past = client.get("/api/v1/transactions?business_date=2026-10-22")
    assert [row["id"] for row in past.json()["items"]] == [3]
    assert past.json()["items"][0]["total_business_share"] == "45.00"
    assert client.get("/api/v1/transactions?limit=101").status_code == 422
    assert client.get("/api/v1/transactions?cursor=not-valid").status_code == 422
    assert client.get("/api/v1/transactions", params={"business_date": "2026-10-22", "cursor": cursor}).status_code == 422


def test_ascending_history_cursors_have_no_gaps_or_duplicates(api):
    client, factory, _app, _monkeypatch = api
    with factory.begin() as session:
        for transaction_id in (4, 5, 6):
            session.add(Transaction(
                id=transaction_id,
                date_time=datetime(2026, 10, 22, 17, transaction_id - 3, tzinfo=timezone.utc),
                business_date=date(2026, 10, 23), recorded_by_user_id=2,
                entry_source="Direct", payment_method="Cash", status="Completed",
            ))
            session.add(TransactionItem(
                id=transaction_id, transaction_id=transaction_id, service_id=1, staff_id=1,
                item_name_snapshot=f"Synthetic Item {transaction_id}", selling_price=Decimal("100.00"),
                commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                staff_commission=Decimal("50.00"), business_share=Decimal("50.00"),
            ))
    seen = []
    cursor = None
    for _ in range(3):
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/api/v1/transactions", params=params)
        assert response.status_code == 200, response.json()
        seen.extend(row["id"] for row in response.json()["items"])
        cursor = response.json()["next_cursor"]
    assert seen == [1, 2, 4, 5, 6]
    assert cursor is None
    # Old descending-order cursors must not silently skip or duplicate rows.
    legacy = base64.urlsafe_b64encode(json.dumps([
        datetime(2026, 10, 22, 17, tzinfo=timezone.utc).isoformat(), 1, "2026-10-23",
    ]).encode()).decode().rstrip("=")
    assert client.get("/api/v1/transactions", params={"cursor": legacy}).status_code == 422


def test_history_orders_occurrence_before_id(api):
    client, factory, _app, _monkeypatch = api
    with factory.begin() as session:
        session.add(Transaction(
            id=9, date_time=datetime(2026, 10, 22, 16, 59, tzinfo=timezone.utc),
            business_date=date(2026, 10, 23), recorded_by_user_id=2,
            entry_source="Direct", payment_method="Cash", status="Completed",
        ))
        session.add(TransactionItem(
            id=9, transaction_id=9, service_id=1, staff_id=1,
            item_name_snapshot="Earlier Synthetic Item", selling_price=Decimal("100.00"),
            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
            staff_commission=Decimal("50.00"), business_share=Decimal("50.00"),
        ))
    response = client.get("/api/v1/transactions")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [9, 1, 2]


def test_cashier_today_shared_visibility_and_financial_snapshots(api):
    client, _factory, app, _monkeypatch = api
    _cashier(app)
    listing = client.get("/api/v1/transactions")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["items"]] == [1, 2]
    for row in listing.json()["items"]:
        assert set(row) == {"id", "date_time", "business_date", "status", "payment_method",
                            "gross_sales", "total_staff_commission", "total_business_share"}
        assert "gcash_reference" not in row
    detail = client.get("/api/v1/transactions/2")
    assert detail.headers["cache-control"] == "no-store"
    body = detail.json()
    assert body["gcash_reference"] == "synthetic-ref"
    assert body["items"][0] == {"id": 2, "item_name_snapshot": "Other Item", "selling_price": "120.00",
                                "staff_id": 1, "staff_name": "Synthetic Stylist", "service_id": 1,
                                "product_id": None, "commission_type_snapshot": "Percentage",
                                "commission_value_snapshot": "50.00", "staff_commission": "60.00",
                                "business_share": "60.00"}
    assert body["total_staff_commission"] == "60.00"
    assert body["total_business_share"] == "60.00"
    assert "void_reason" not in body
    assert client.get("/api/v1/transactions/1").status_code == 200
    assert client.get("/api/v1/transactions/3").status_code == 404
    assert client.get("/api/v1/transactions?business_date=2026-10-22").status_code == 403
    _cashier(app, user_id=3)
    assert client.get("/api/v1/transactions/1").status_code == 200


def test_owner_detail_preserves_snapshots_after_catalog_change(api):
    client, factory, _app, _monkeypatch = api
    with factory.begin() as session:
        service = session.get(Service, 1)
        service.name = "Renamed Catalog Item"
        service.current_price = Decimal("999.00")
    detail = client.get("/api/v1/transactions/1")
    assert detail.status_code == 200
    item = detail.json()["items"][0]
    assert item["item_name_snapshot"] == "Original Name"
    assert item["selling_price"] == "101.00"
    assert item["commission_type_snapshot"] == "Percentage"
    assert item["commission_value_snapshot"] == "50.00"
    assert item["staff_commission"] == "51.00"
    assert item["business_share"] == "50.00"
    assert detail.json()["gross_sales"] == "101.00"


def test_void_success_then_conflict_with_separate_failure_audit(api):
    client, factory, app, _monkeypatch = api
    first = client.post("/api/v1/transactions/1/void", json={"reason": "  Mistaken sale  "})
    assert first.status_code == 200, first.json()
    assert first.json()["status"] == "Voided"
    assert first.json()["void_reason"] == "Mistaken sale"
    assert first.json()["voided_by_user_id"] == 1
    assert first.json()["voided_at"] is not None
    second = client.post("/api/v1/transactions/1/void", json={"reason": "Again"})
    assert second.status_code == 409
    with factory() as session:
        transaction = session.get(Transaction, 1)
        item = session.get(TransactionItem, 1)
        assert transaction.void_reason == "Mistaken sale"
        assert item.staff_commission == Decimal("51.00")
        assert item.business_share == Decimal("50.00")
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.id)))
        assert [(event.outcome, event.actor_user_id) for event in events] == [("Success", 1), ("Failure", 1)]
    assert client.get("/api/v1/transactions").json()["items"][0]["status"] == "Voided"
    _cashier(app)
    cashier_detail = client.get("/api/v1/transactions/1").json()
    assert cashier_detail["status"] == "Voided"
    assert cashier_detail["items"][0]["staff_commission"] == "51.00"
    assert cashier_detail["items"][0]["business_share"] == "50.00"
    assert "void_reason" not in cashier_detail


def test_cashier_void_denied_and_audited_without_record_access(api):
    client, factory, app, _monkeypatch = api
    _cashier(app)
    response = client.post("/api/v1/transactions/3/void", json={"reason": "Attempt"})
    assert response.status_code == 403
    assert "Past Item" not in response.text and "90.00" not in response.text
    with factory() as session:
        assert session.get(Transaction, 3).status == "Completed"
        event = session.scalar(select(AuditEvent))
        assert event.outcome == "Failure" and event.actor_user_id == 2
    del app.dependency_overrides[get_current_principal]
    assert client.post("/api/v1/transactions/1/void", json={"reason": "Attempt"}).status_code == 401
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_void_validation_and_audit_failure_roll_back(api):
    client, factory, _app, monkeypatch = api
    assert client.post("/api/v1/transactions/1/void", json={"reason": "  "}).status_code == 422
    assert client.post("/api/v1/transactions/1/void", json={"reason": "x" * 501}).status_code == 422
    assert client.post("/api/v1/transactions/1/void", json={"reason": "x", "extra": 1}).status_code == 422
    assert client.post("/api/v1/transactions/999/void", json={"reason": "Missing"}).status_code == 404
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    import app.modules.transactions.history_service as history
    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(history, "AuditEvent", fail_audit)
    assert client.post("/api/v1/transactions/1/void", json={"reason": "Mistake"}).status_code == 500
    with factory() as session:
        assert session.get(Transaction, 1).status == "Completed"
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_manila_midnight_moves_cashier_visibility(api):
    client, _factory, app, monkeypatch = api
    import app.modules.transactions.history_service as history
    _cashier(app)
    monkeypatch.setattr(history, "_database_time",
                        lambda _session: datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc))
    assert [row["id"] for row in client.get("/api/v1/transactions").json()["items"]] == [3]
    assert client.get("/api/v1/transactions/1").status_code == 404
    monkeypatch.setattr(history, "_database_time",
                        lambda _session: datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc))
    assert [row["id"] for row in client.get("/api/v1/transactions").json()["items"]] == [1, 2]
    assert client.get("/api/v1/transactions/3").status_code == 404
