"""Fast daily-report API checks using synthetic, in-memory records only."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.reports.router import router
from app.modules.staff.models import Staff
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _sqlite_setup(connection, _record):
        connection.isolation_level = None
        connection.create_function("BTRIM", 1, lambda value: value.strip() if value else value,
                                   deterministic=True)

    @event.listens_for(engine, "begin")
    def _sqlite_begin(connection):
        connection.exec_driver_sql("BEGIN")

    for model in (User, Staff, CommissionRule, Service, Product, Transaction, TransactionItem):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.modules.reports.service as reports
    monkeypatch.setattr(reports, "_database_time", lambda _session: datetime(2026, 10, 22, 16, tzinfo=timezone.utc))
    with factory.begin() as session:
        session.add(User(id=1, username="synthetic-owner", password_hash="synthetic", role="Owner"))
        session.add(User(id=2, username="synthetic-cashier", password_hash="synthetic", role="Cashier"))
        session.add_all([
            Staff(id=1, name="Current Barber", role="Barber", active=True),
            Staff(id=2, name="Current Inactive Stylist", role="Stylist", active=False),
        ])
        session.add_all([
            CommissionRule(id=1, name="synthetic-percent", type="Percentage", value=Decimal("50.00")),
            CommissionRule(id=2, name="synthetic-fixed", type="Fixed", value=Decimal("10.00")),
        ])
        session.add(Service(id=1, name="Current Service", current_price=Decimal("100.25"), commission_rule_id=1))
        session.add(Product(id=1, name="Current Product", current_price=Decimal("50.00"), commission_rule_id=2))
        session.add_all([
            Transaction(id=1, date_time=datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc),
                        business_date=date(2026, 10, 22), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="Cash", status="Completed"),
            Transaction(id=2, date_time=datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc),
                        business_date=date(2026, 10, 22), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="GCash", gcash_reference="synthetic-ref",
                        status="Completed"),
            Transaction(id=3, date_time=datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc),
                        business_date=date(2026, 10, 22), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="Cash", status="Voided",
                        void_reason="Synthetic void", voided_by_user_id=1,
                        voided_at=datetime(2026, 10, 23, 1, tzinfo=timezone.utc)),
            Transaction(id=4, date_time=datetime(2026, 10, 22, 16, tzinfo=timezone.utc),
                        business_date=date(2026, 10, 23), recorded_by_user_id=2,
                        entry_source="Direct", payment_method="Cash", status="Completed"),
        ])
        session.add_all([
            TransactionItem(id=1, transaction_id=1, service_id=1, staff_id=1,
                            item_name_snapshot="Old Service Name", selling_price=Decimal("100.25"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("50.00"), business_share=Decimal("50.25")),
            TransactionItem(id=2, transaction_id=1, product_id=1, staff_id=None,
                            item_name_snapshot="Old Product Name", selling_price=Decimal("50.00"),
                            staff_commission=Decimal("0.00"), business_share=Decimal("50.00")),
            TransactionItem(id=3, transaction_id=2, product_id=1, staff_id=2,
                            item_name_snapshot="Credited Product", selling_price=Decimal("20.00"),
                            commission_type_snapshot="Fixed", commission_value_snapshot=Decimal("10.00"),
                            staff_commission=Decimal("10.00"), business_share=Decimal("10.00")),
            TransactionItem(id=4, transaction_id=3, service_id=1, staff_id=1,
                            item_name_snapshot="Voided Service", selling_price=Decimal("40.00"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("20.00"), business_share=Decimal("20.00")),
            TransactionItem(id=5, transaction_id=4, service_id=1, staff_id=1,
                            item_name_snapshot="New Day Service", selling_price=Decimal("7.00"),
                            commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                            staff_commission=Decimal("4.00"), business_share=Decimal("3.00")),
        ])
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic-owner", "Owner", "synthetic")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory, app, engine
    finally:
        engine.dispose()


def test_owner_historical_decimal_totals_and_void_exclusion(api):
    client, _factory, _app, _engine = api
    response = client.get("/api/v1/reports/daily?business_date=2026-10-22")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    report = response.json()
    assert report["business_date"] == "2026-10-22"
    assert report["completed_transaction_count"] == 2
    assert report["voided_transaction_count"] == 1
    assert report["gross_sales"] == "170.25"
    assert report["cash_sales"] == "150.25"
    assert report["gcash_sales"] == "20.00"
    assert report["total_staff_commission"] == "60.00"
    assert report["total_business_share"] == "110.25"
    assert report["staff_commissions"] == [
        {"staff_id": 1, "current_staff_name": "Current Barber", "total_staff_commission": "50.00"},
        {"staff_id": 2, "current_staff_name": "Current Inactive Stylist", "total_staff_commission": "10.00"},
    ]
    assert Decimal(report["gross_sales"]) == Decimal(report["cash_sales"]) + Decimal(report["gcash_sales"])
    assert Decimal(report["gross_sales"]) == (Decimal(report["total_staff_commission"])
                                               + Decimal(report["total_business_share"]))
    assert Decimal(report["total_staff_commission"]) == sum(
        (Decimal(row["total_staff_commission"]) for row in report["staff_commissions"]), Decimal("0.00"))


def test_cashier_today_only_and_manila_midnight(api):
    client, _factory, app, _engine = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "synthetic-cashier", "Cashier", "synthetic")
    response = client.get("/api/v1/reports/daily")
    assert response.status_code == 200
    assert response.json()["business_date"] == "2026-10-23"
    assert response.json()["gross_sales"] == "7.00"
    assert response.json()["total_staff_commission"] == "4.00"
    assert response.json()["total_business_share"] == "3.00"
    assert client.get("/api/v1/reports/daily?business_date=2026-10-22").status_code == 403
    assert client.get("/api/v1/reports/daily?business_date=2026-10-24").status_code == 403
    assert client.get("/api/v1/reports/daily?business_date=invalid").status_code == 422
    app.dependency_overrides.pop(get_current_principal)
    assert client.get("/api/v1/reports/daily").status_code == 401


def test_empty_date_returns_zero_and_no_staff(api):
    client, _factory, _app, _engine = api
    response = client.get("/api/v1/reports/daily?business_date=2026-10-21")
    assert response.status_code == 200
    report = response.json()
    assert report["gross_sales"] == report["cash_sales"] == report["gcash_sales"] == "0.00"
    assert report["total_staff_commission"] == report["total_business_share"] == "0.00"
    assert report["completed_transaction_count"] == report["voided_transaction_count"] == 0
    assert report["staff_commissions"] == []


def test_owner_cannot_request_future_report(api):
    client, _factory, _app, _engine = api
    assert client.get("/api/v1/reports/daily?business_date=2026-10-24").status_code == 422


def test_historical_void_changes_prior_day_without_rewriting_items(api):
    client, factory, _app, _engine = api
    before = client.get("/api/v1/reports/daily?business_date=2026-10-23").json()
    with factory.begin() as session:
        sale = session.get(Transaction, 4)
        item = session.scalar(select(TransactionItem).where(TransactionItem.transaction_id == 4))
        original = (item.selling_price, item.staff_commission, item.business_share)
        sale.status = "Voided"
        sale.void_reason = "Synthetic historical correction"
        sale.voided_by_user_id = 1
        sale.voided_at = datetime(2026, 10, 24, tzinfo=timezone.utc)
    after = client.get("/api/v1/reports/daily?business_date=2026-10-23").json()
    assert before["gross_sales"] == "7.00"
    assert after["gross_sales"] == "0.00"
    assert after["voided_transaction_count"] == 1
    with factory() as session:
        item = session.scalar(select(TransactionItem).where(TransactionItem.transaction_id == 4))
        assert (item.selling_price, item.staff_commission, item.business_share) == original


def test_financial_aggregation_is_one_sql_statement(api):
    client, _factory, _app, engine = api
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("WITH"):
            statements.append(statement)

    response = client.get("/api/v1/reports/daily?business_date=2026-10-22")
    assert response.status_code == 200
    assert len(statements) == 1
