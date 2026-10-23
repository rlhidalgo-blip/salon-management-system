"""Separately opted-in REAL-COMMIT void race on local yabs_salon_test only.

An interrupted process can leave synthetic rows behind. Do not run without
explicit approval for controlled commits and manual residual-data review.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from ipaddress import ip_address
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.history_service import void_transaction
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


PREFIX = "synthetic-void-race-"


def _safe(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured database target")
    if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
        raise RuntimeError("Unsafe connected database")
    if connection.scalar(text("SELECT current_user")) != "yabs_app":
        raise RuntimeError("Unsafe connected user")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if address is None or not ip_address(str(address)).is_loopback:
        raise RuntimeError("Database server is not on loopback")
    if connection.scalar(text("SELECT current_schema()")) != "public":
        raise RuntimeError("Unexpected schema")
    if (connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
            or connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01"):
        raise RuntimeError("Unexpected Alembic revision")


def test_two_connection_void_race_commits_once_and_cleans_up():
    if os.getenv("RUN_VOID_CONCURRENCY_TESTS") != "1":
        pytest.skip("Controlled synthetic commits require RUN_VOID_CONCURRENCY_TESTS=1")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured database target; no writes attempted")
    engine = create_engine(url, pool_size=3, max_overflow=0,
                           connect_args={"connect_timeout": 5,
                                         "options": "-c statement_timeout=15000 -c lock_timeout=10000"})
    marker = PREFIX + uuid4().hex
    ids = {}
    setup_committed = False
    try:
        with engine.connect() as connection:
            _safe(connection, url)
            if connection.scalar(select(func.count()).select_from(User).where(User.username.like(PREFIX + "%"))):
                pytest.fail("Previous synthetic void-race run may remain; no writes attempted")
        with engine.begin() as connection:
            _safe(connection, url)
            ids["user"] = connection.execute(insert(User).values(
                username=marker, password_hash="synthetic-not-a-real-account", role="Owner",
                active=True).returning(User.id)).scalar_one()
            ids["staff"] = connection.execute(insert(Staff).values(
                name=marker, role="Stylist", active=True).returning(Staff.id)).scalar_one()
            ids["rule"] = connection.execute(insert(CommissionRule).values(
                name=marker, type="Percentage", value=Decimal("50.00"),
                active=True).returning(CommissionRule.id)).scalar_one()
            ids["service"] = connection.execute(insert(Service).values(
                name=marker, current_price=Decimal("101.00"), commission_rule_id=ids["rule"],
                active=True).returning(Service.id)).scalar_one()
            ids["transaction"] = connection.execute(insert(Transaction).values(
                date_time=func.clock_timestamp(),
                business_date=text("(clock_timestamp() AT TIME ZONE 'Asia/Manila')::date"),
                recorded_by_user_id=ids["user"], entry_source="Direct", payment_method="Cash",
                status="Completed").returning(Transaction.id)).scalar_one()
            ids["item"] = connection.execute(insert(TransactionItem).values(
                transaction_id=ids["transaction"], service_id=ids["service"], staff_id=ids["staff"],
                item_name_snapshot=marker, selling_price=Decimal("101.00"),
                commission_type_snapshot="Percentage", commission_value_snapshot=Decimal("50.00"),
                staff_commission=Decimal("51.00"), business_share=Decimal("50.00")
            ).returning(TransactionItem.id)).scalar_one()
        setup_committed = True

        entered = Event()
        second_started = Event()
        release = Event()
        def first_void():
            with Session(engine, autoflush=False) as session:
                with session.begin():
                    result = void_transaction(session, transaction_id=ids["transaction"],
                                              reason="first synthetic correction", actor_user_id=ids["user"])
                    entered.set()
                    assert release.wait(timeout=8), "Timed out holding first void lock"
                return result
        def second_void():
            assert entered.wait(timeout=8)
            second_started.set()
            with Session(engine, autoflush=False) as session:
                with session.begin():
                    return void_transaction(session, transaction_id=ids["transaction"],
                                            reason="second synthetic correction", actor_user_id=ids["user"])
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(first_void)
            assert entered.wait(timeout=8)
            second = executor.submit(second_void)
            try:
                assert second_started.wait(timeout=8)
                assert not second.done(), "Second void completed while first held the row lock"
            finally:
                release.set()
            assert first.result(timeout=15) is True
            assert second.result(timeout=15) is False
        with engine.connect() as verifier:
            _safe(verifier, url)
            assert verifier.scalar(select(Transaction.status).where(
                Transaction.id == ids["transaction"])) == "Voided"
            assert verifier.scalar(select(Transaction.void_reason).where(
                Transaction.id == ids["transaction"])) == "first synthetic correction"
            assert list(verifier.scalars(select(AuditEvent.outcome).where(
                AuditEvent.actor_user_id == ids["user"],
                AuditEvent.resource_id == str(ids["transaction"])).order_by(AuditEvent.id))) == ["Success", "Failure"]
            assert verifier.scalar(select(TransactionItem.staff_commission).where(
                TransactionItem.id == ids["item"])) == Decimal("51.00")
    finally:
        try:
            if setup_committed:
                with engine.begin() as connection:
                    _safe(connection, url)
                    if connection.scalar(select(User.username).where(User.id == ids["user"])) != marker:
                        raise RuntimeError("Synthetic ownership mismatch")
                    if connection.scalar(select(Transaction.recorded_by_user_id).where(
                            Transaction.id == ids["transaction"])) != ids["user"]:
                        raise RuntimeError("Synthetic transaction ownership mismatch")
                    if connection.scalar(select(Service.name).where(Service.id == ids["service"])) != marker:
                        raise RuntimeError("Synthetic catalog ownership mismatch")
                    connection.execute(delete(AuditEvent).where(AuditEvent.actor_user_id == ids["user"]))
                    connection.execute(delete(TransactionItem).where(TransactionItem.id == ids["item"]))
                    connection.execute(delete(Transaction).where(Transaction.id == ids["transaction"]))
                    connection.execute(delete(Service).where(Service.id == ids["service"]))
                    connection.execute(delete(Staff).where(Staff.id == ids["staff"]))
                    connection.execute(delete(CommissionRule).where(CommissionRule.id == ids["rule"]))
                    connection.execute(delete(User).where(User.id == ids["user"]))
                with engine.connect() as verifier:
                    _safe(verifier, url)
                    for model, row_id in ((AuditEvent, None), (TransactionItem, ids["item"]),
                                          (Transaction, ids["transaction"]), (Service, ids["service"]),
                                          (Staff, ids["staff"]), (CommissionRule, ids["rule"]), (User, ids["user"])):
                        if model is AuditEvent:
                            assert verifier.scalar(select(func.count()).select_from(model).where(
                                AuditEvent.actor_user_id == ids["user"])) == 0
                        else:
                            assert verifier.scalar(select(func.count()).select_from(model).where(
                                model.id == row_id)) == 0
        except Exception as exc:
            raise AssertionError(f"Synthetic cleanup failed: run={marker}, ids={ids}") from exc
        finally:
            engine.dispose()
