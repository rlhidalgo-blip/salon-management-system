"""Opt-in rollback-only PostgreSQL checks for daily reporting."""

import os
from datetime import datetime, time, timedelta
from decimal import Decimal
from ipaddress import ip_address
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.reports.service import daily_report, monthly_report
from app.modules.staff.models import Staff
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


MANILA = ZoneInfo("Asia/Manila")
MODELS = (User, Staff, CommissionRule, Service, Transaction, TransactionItem)


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
    if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01":
        pytest.fail("Unexpected Alembic revision; no writes attempted")


@pytest.fixture
def db_case():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured PostgreSQL target; no writes attempted")
    engine = create_engine(url, connect_args={"connect_timeout": 5,
                                              "options": "-c statement_timeout=15000 -c lock_timeout=10000"})
    marker = "synthetic-report-" + uuid4().hex
    try:
        with engine.connect() as connection:
            _safe_target(connection, url)
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in MODELS}
            connection.rollback()
            outer = connection.begin()
            try:
                yesterday = connection.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Manila')::date")) - timedelta(days=1)
                occurred = datetime.combine(yesterday, time(12), tzinfo=MANILA)
                user_id = connection.execute(insert(User).values(
                    username=marker, password_hash="synthetic-not-a-real-password", role="Cashier",
                    active=True).returning(User.id)).scalar_one()
                staff_id = connection.execute(insert(Staff).values(
                    name=marker, role="Stylist", active=False).returning(Staff.id)).scalar_one()
                rule_id = connection.execute(insert(CommissionRule).values(
                    name=marker, type="Percentage", value=Decimal("50.00"),
                    active=True).returning(CommissionRule.id)).scalar_one()
                service_id = connection.execute(insert(Service).values(
                    name=marker, current_price=Decimal("101.00"), commission_rule_id=rule_id,
                    active=False).returning(Service.id)).scalar_one()
                completed_id = connection.execute(insert(Transaction).values(
                    date_time=occurred, business_date=yesterday, recorded_by_user_id=user_id,
                    entry_source="Direct", payment_method="GCash", gcash_reference=marker,
                    status="Completed").returning(Transaction.id)).scalar_one()
                voided_id = connection.execute(insert(Transaction).values(
                    date_time=occurred, business_date=yesterday, recorded_by_user_id=user_id,
                    entry_source="Direct", payment_method="Cash", status="Voided",
                    void_reason="Synthetic void", voided_by_user_id=user_id,
                    voided_at=occurred + timedelta(days=1)).returning(Transaction.id)).scalar_one()
                for transaction_id in (completed_id, voided_id):
                    connection.execute(insert(TransactionItem).values(
                        transaction_id=transaction_id, service_id=service_id, staff_id=staff_id,
                        item_name_snapshot=marker, selling_price=Decimal("101.00"),
                        commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                        staff_commission=Decimal("51.00"), business_share=Decimal("50.00")))
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    yield session, yesterday, completed_id
            finally:
                if not outer.is_active:
                    pytest.fail("Outer rollback safety was lost")
                outer.rollback()
        with engine.connect() as verifier:
            _safe_target(verifier, url)
            for model in MODELS:
                assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
            assert verifier.scalar(select(func.count()).select_from(User).where(
                User.username == marker)) == 0
    finally:
        engine.dispose()


def test_postgres_daily_snapshot_aggregation_and_historical_void(db_case):
    session, business_date, completed_id = db_case
    with session.begin():
        before = daily_report(session, role="Owner", business_date=business_date)
    assert before.gross_sales == Decimal("101.00")
    assert before.cash_sales == Decimal("0.00")
    assert before.gcash_sales == Decimal("101.00")
    assert before.total_staff_commission == Decimal("51.00")
    assert before.total_business_share == Decimal("50.00")
    assert before.completed_transaction_count == before.voided_transaction_count == 1
    assert len(before.staff_commissions) == 1
    assert before.staff_commissions[0].total_staff_commission == Decimal("51.00")
    assert before.staff_commissions[0].current_staff_name.startswith("synthetic-report-")
    assert before.gross_sales == before.cash_sales + before.gcash_sales
    assert before.gross_sales == before.total_staff_commission + before.total_business_share

    with session.begin():
        sale = session.get(Transaction, completed_id)
        sale.status = "Voided"
        sale.void_reason = "Synthetic correction"
        sale.voided_by_user_id = sale.recorded_by_user_id
        sale.voided_at = datetime.combine(business_date + timedelta(days=1), time(12), tzinfo=MANILA)
    with session.begin():
        after = daily_report(session, role="Owner", business_date=business_date)
    assert after.gross_sales == after.total_staff_commission == after.total_business_share == Decimal("0.00")
    assert after.completed_transaction_count == 0
    assert after.voided_transaction_count == 2
    assert after.staff_commissions == []


def test_postgres_monthly_snapshots_attribution_and_original_month_void(db_case):
    session, business_date, completed_id = db_case
    month = business_date.strftime("%Y-%m")
    with session.begin():
        before = monthly_report(session, month=month)
    assert before.gross_sales == before.gcash_sales == Decimal("101.00")
    assert before.cash_sales == before.unassigned_product_sales == Decimal("0.00")
    assert before.total_staff_commission == Decimal("51.00")
    assert before.total_business_share == Decimal("50.00")
    assert before.completed_transaction_count == before.voided_transaction_count == 1
    assert len(before.staff_performance) == 1
    assert before.staff_performance[0].attributed_sales == Decimal("101.00")
    assert before.staff_performance[0].total_staff_commission == Decimal("51.00")
    assert before.staff_performance[0].current_staff_name.startswith("synthetic-report-")
    assert before.gross_sales == before.total_staff_commission + before.total_business_share
    assert before.gross_sales == before.cash_sales + before.gcash_sales
    assert before.gross_sales == (before.staff_performance[0].attributed_sales
                                 + before.unassigned_product_sales)

    with session.begin():
        sale = session.get(Transaction, completed_id)
        sale.status = "Voided"
        sale.void_reason = "Synthetic correction"
        sale.voided_by_user_id = sale.recorded_by_user_id
        sale.voided_at = datetime.combine(business_date + timedelta(days=1), time(12), tzinfo=MANILA)
    with session.begin():
        after = monthly_report(session, month=month)
    assert after.gross_sales == after.total_staff_commission == after.total_business_share == Decimal("0.00")
    assert after.unassigned_product_sales == Decimal("0.00")
    assert after.completed_transaction_count == 0
    assert after.voided_transaction_count == 2
    assert after.staff_performance == []
