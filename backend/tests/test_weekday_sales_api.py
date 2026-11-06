"""Fast Owner weekday analytics checks with synthetic in-memory snapshots."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.operating_days.models import OperatingDay
from app.modules.reports.router import router
from app.modules.staff.models import Staff
from app.modules.transactions.calculations import calculate_item
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


TODAY = date(2026, 11, 16)  # Monday in Asia/Manila.


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

    for model in (User, Staff, CommissionRule, Service, Transaction, TransactionItem, OperatingDay):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.modules.reports.service as reports
    monkeypatch.setattr(reports, "_database_time",
                        lambda _session: datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc))
    with factory.begin() as session:
        session.add_all([
            User(id=1, username="synthetic-owner", password_hash="synthetic", role="Owner"),
            User(id=2, username="synthetic-cashier", password_hash="synthetic", role="Cashier"),
            Staff(id=1, name="Synthetic Stylist", role="Stylist"),
            CommissionRule(id=1, name="Synthetic Rule", type="Percentage", value=Decimal("50.00")),
            Service(id=1, name="Synthetic Service", current_price=Decimal("1.00"), commission_rule_id=1),
        ])
        for day, status, reason in (
            (date(2026, 11, 2), "Open", None),
            (date(2026, 11, 3), "Open", None),
            (date(2026, 11, 5), "PlannedClosed", "Unconfirmed plan"),
            (date(2026, 11, 6), "Closed", "Holiday"),
            (date(2026, 11, 7), "Closed", "Historical inconsistency"),
            (date(2026, 11, 8), "Open", None),
            (date(2026, 11, 9), "Open", None),
            (TODAY, "Open", None),  # Today remains provisional despite verification.
        ):
            session.add(OperatingDay(business_date=day, status=status, closure_reason=reason,
                                     created_by_user_id=1, updated_by_user_id=1, version=1))
        sales = (
            (1, date(2026, 11, 2), "Completed", ("4.00", "6.01")),
            (2, date(2026, 11, 9), "Completed", ("10.00",)),
            (3, date(2026, 11, 4), "Completed", ("5.00",)),
            (4, date(2026, 11, 5), "Completed", ("7.00",)),
            (5, date(2026, 11, 7), "Completed", ("11.00",)),
            (6, date(2026, 11, 8), "Completed", ("0.03",)),
            (7, TODAY, "Completed", ("3.00",)),
            (8, date(2026, 11, 2), "Voided", ("200.00",)),
            (9, date(2026, 10, 26), "Completed", ("5.00",)),
        )
        item_id = 1
        for sale_id, day, status, prices in sales:
            # Midnight Manila falls on the prior UTC date; business_date is authoritative.
            occurred = datetime(day.year, day.month, day.day, 0, 0, tzinfo=timezone.utc)
            if day == date(2026, 11, 2):
                occurred = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)
            session.add(Transaction(
                id=sale_id, date_time=occurred, business_date=day, recorded_by_user_id=2,
                entry_source="Direct", payment_method="Cash", status=status,
                void_reason="Synthetic void" if status == "Voided" else None,
                voided_by_user_id=1 if status == "Voided" else None,
                voided_at=datetime(2026, 11, 3, tzinfo=timezone.utc) if status == "Voided" else None,
            ))
            for price in prices:
                value = Decimal(price)
                commission, share = calculate_item(value, "Percentage", Decimal("50.00"))
                session.add(TransactionItem(
                    id=item_id, transaction_id=sale_id, service_id=1, staff_id=1,
                    item_name_snapshot="Historical snapshot", selling_price=value,
                    commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                    staff_commission=commission, business_share=share,
                ))
                item_id += 1
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
            yield client, app
    finally:
        engine.dispose()


def get(client, start="2026-11-02", through="2026-11-16"):
    return client.get(f"/api/v1/reports/weekday-sales?from={start}&through={through}")


def test_weekday_snapshots_coverage_rounding_provisional_and_reconciliation(api):
    client, _app = api
    response = get(client)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    report = response.json()
    assert report["from"] == "2026-11-02" and report["through"] == "2026-11-16"
    assert report["as_of"].startswith("2026-11-15T16:00:00")
    days = report["weekdays"]
    assert [(row["weekday_number"], row["weekday"]) for row in days] == list(enumerate(
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"), 1))
    monday = days[0]
    assert (monday["gross_sales"], monday["historical_gross_sales"],
            monday["verified_open_gross_sales"], monday["provisional_today_gross_sales"]) == (
                "23.01", "20.01", "20.01", "3.00")
    assert monday["verified_open_days"] == 2
    assert monday["average_gross_per_verified_open_day"] == "10.01"  # 10.005, ROUND_HALF_UP.
    assert days[1]["verified_open_days"] == 1
    assert days[1]["average_gross_per_verified_open_day"] == "0.00"
    assert days[2]["unknown_days"] == 2 and days[2]["gross_sales"] == "5.00"
    assert days[3]["unconfirmed_planned_days"] == 1 and days[3]["gross_sales"] == "7.00"
    assert days[5]["verified_closed_days"] == 1
    assert days[5]["closed_dates_with_sales"] == 1 and days[5]["gross_sales"] == "11.00"
    assert days[5]["verified_open_gross_sales"] == "0.00"
    assert days[5]["average_gross_per_verified_open_day"] is None
    coverage = report["coverage"]
    assert coverage == {
        "historical_days": 14, "verified_open_days": 4, "verified_closed_days": 2,
        "unknown_days": 7, "unconfirmed_planned_days": 1, "unverified_days": 8,
        "closed_dates_with_sales": 1, "incomplete_coverage": True,
    }
    assert sum(Decimal(row["gross_sales"]) for row in days) == Decimal("46.04")
    assert sum(Decimal(row["historical_gross_sales"]) for row in days) == Decimal("43.04")
    assert client.get("/api/v1/reports/daily?business_date=2026-11-02").json()["gross_sales"] == "10.01"
    assert client.get("/api/v1/reports/monthly?month=2026-11").json()["gross_sales"] == "46.04"


def test_empty_period_and_zero_denominators(api):
    client, _app = api
    response = get(client, "2026-10-01", "2026-10-07")
    assert response.status_code == 200, response.text
    report = response.json()
    assert len(report["weekdays"]) == 7
    assert all(row["gross_sales"] == "0.00" and row["average_gross_per_verified_open_day"] is None
               for row in report["weekdays"])
    assert report["coverage"]["unknown_days"] == 7
    assert report["coverage"]["incomplete_coverage"] is True


def test_partial_weekday_average_excludes_unknown_sales(api):
    response = get(api[0], "2026-10-26", "2026-11-16")
    assert response.status_code == 200, response.text
    monday = response.json()["weekdays"][0]
    assert monday["gross_sales"] == "28.01"
    assert monday["historical_gross_sales"] == "25.01"
    assert monday["verified_open_gross_sales"] == "20.01"
    assert monday["verified_open_days"] == 2 and monday["unknown_days"] == 1
    assert monday["average_gross_per_verified_open_day"] == "10.01"


def test_manila_midnight_during_query_requires_retry(api, monkeypatch):
    import app.modules.reports.service as reports
    clock = iter((datetime(2026, 11, 15, 15, 59, 59, tzinfo=timezone.utc),
                  datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)))
    monkeypatch.setattr(reports, "_database_time", lambda _session: next(clock))
    response = get(api[0], "2026-11-02", "2026-11-15")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "report_date_changed"


@pytest.mark.parametrize("start,through,code", [
    ("2026-11-16", "2026-11-15", "invalid_date_range"),
    ("2025-11-15", "2026-11-16", "invalid_date_range"),  # 367 inclusive dates.
    ("2026-11-16", "2026-11-17", "invalid_business_date"),
    ("2026-11-1", "2026-11-16", "invalid_business_date"),
    ("2026-02-30", "2026-11-16", "invalid_business_date"),
])
def test_invalid_ranges_and_dates(api, start, through, code):
    response = get(api[0], start, through)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_maximum_366_date_range_is_accepted(api):
    response = get(api[0], "2025-11-16", "2026-11-16")
    assert response.status_code == 200, response.text
    assert len(response.json()["weekdays"]) == 7


def test_owner_only_and_missing_session(api):
    client, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "synthetic-cashier", "Cashier", "synthetic")
    response = get(client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    app.dependency_overrides.pop(get_current_principal)
    assert get(client).status_code == 401
