"""Opt-in real-commit reservation and calendar races on isolated local yabs_salon_test.

Never run alongside other database writers. A crash can leave synthetic rows;
the marker and captured IDs in a cleanup failure require manual review.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, time as clock_time, timedelta, timezone
from decimal import Decimal
from ipaddress import ip_address
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import TypeAdapter
from sqlalchemy import create_engine, delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.operating_days.date_lock import lock_operating_date
from app.modules.operating_days.models import OperatingDay
from app.modules.operating_days.schemas import BulkOpenVerification, OperatingDayUpdate
from app.modules.operating_days.service import bulk_verify_open, update_day
from app.modules.staff.models import Staff
from app.modules.transactions.attempt_models import SaleAttempt
from app.modules.transactions.attempt_schemas import CancellationRequest, ReservationRequest
from app.modules.transactions.attempt_service import cancel_sale_attempt, reserve_sale_attempt
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.manual_service import record_manual_sale
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.service import record_direct_sale
from app.modules.users.models import User


PREFIX = "synthetic-attempt-race-"
REVISION = "20261104_01"
MODELS = {
    "users": User, "staff": Staff, "rules": CommissionRule, "services": Service,
    "attempts": SaleAttempt, "transactions": Transaction, "items": TransactionItem,
    "claims": SaleIdempotency, "audits": AuditEvent,
}


def _configured_target(url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured test target")


def _connected_target(connection, url):
    _configured_target(url)
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if (address is None or not ip_address(str(address)).is_loopback
            or connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"
            or connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1
            or connection.scalar(text("SELECT version_num FROM public.alembic_version")) != REVISION
            or connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is None
            or connection.scalar(text("SELECT to_regclass('public.operating_days')")) is None):
        raise RuntimeError("Unsafe connected target or Alembic revision")


@dataclass
class Case:
    engine: object
    url: object
    marker: str
    owner_id: int | None = None
    second_owner_id: int | None = None
    cashier_id: int | None = None
    staff_id: int | None = None
    service_id: int | None = None
    ids: dict[str, set[int]] = field(default_factory=lambda: {name: set() for name in MODELS})
    operating_dates: set = field(default_factory=set)

    def direct(self, price="101.00"):
        return TypeAdapter(ReservationRequest).validate_python({
            "source": "Direct", "sale": {"payment_method": "Cash", "items": [
                {"service_id": self.service_id, "staff_id": self.staff_id, "selling_price": price},
            ]},
        })

    def manual(self, reference=None):
        with self.engine.connect() as connection:
            _connected_target(connection, self.url)
            occurred = connection.scalar(select(func.clock_timestamp())) - timedelta(minutes=1)
        if reference is None:
            reference = "PAPER-" + occurred.astimezone(ZoneInfo("Asia/Manila")).strftime("%Y%m%d") + "-001"
        return TypeAdapter(ReservationRequest).validate_python({
            "source": "Manual", "sale": {
                "date_time": occurred.isoformat(), "manual_reference": reference,
                "verified_against_paper": True, "payment_method": "Cash", "items": [
                    {"service_id": self.service_id, "staff_id": self.staff_id,
                     "item_name_snapshot": self.marker + "-paper-service",
                     "selling_price": "101.00", "commission_type_snapshot": "Percentage",
                     "commission_value_snapshot": "50.00"},
                ],
            },
        })

def _owned_ids(case, connection):
    _connected_target(connection, case.url)
    names = ((case.owner_id, case.marker + "-owner"),
             (case.second_owner_id, case.marker + "-second-owner"),
             (case.cashier_id, case.marker + "-cashier"))
    for user_id, expected in names:
        if connection.scalar(select(User.username).where(User.id == user_id)) != expected:
            raise RuntimeError("Synthetic user ownership mismatch")
    for name, model, column in (
        ("attempts", SaleAttempt, SaleAttempt.user_id),
        ("transactions", Transaction, Transaction.recorded_by_user_id),
        ("claims", SaleIdempotency, SaleIdempotency.user_id),
        ("audits", AuditEvent, AuditEvent.actor_user_id),
    ):
        case.ids[name].update(connection.scalars(select(model.id).where(column.in_(case.ids["users"]))))
    if case.ids["transactions"]:
        case.ids["items"].update(connection.scalars(select(TransactionItem.id).where(
            TransactionItem.transaction_id.in_(case.ids["transactions"]))))
    claimed = set(connection.scalars(select(SaleIdempotency.transaction_id).where(
        SaleIdempotency.id.in_(case.ids["claims"])))) if case.ids["claims"] else set()
    if not claimed.issubset(case.ids["transactions"]):
        raise RuntimeError("Synthetic claim references an unowned sale")
    linked = set(connection.scalars(select(SaleAttempt.transaction_id).where(
        SaleAttempt.id.in_(case.ids["attempts"]), SaleAttempt.transaction_id.is_not(None))))
    if not linked.issubset(case.ids["transactions"]):
        raise RuntimeError("Synthetic attempt references an unowned sale")
    dates = set(connection.scalars(select(OperatingDay.business_date).where(
        OperatingDay.created_by_user_id.in_(case.ids["users"]))))
    case.operating_dates.update(dates)
    if dates and connection.scalar(select(func.count()).select_from(OperatingDay).where(
            OperatingDay.business_date.in_(dates),
            OperatingDay.updated_by_user_id.not_in(case.ids["users"]))) != 0:
        raise RuntimeError("Synthetic operating date ownership mismatch")
    for name, model, row_id in (
        ("staff", Staff, case.staff_id), ("services", Service, case.service_id),
    ):
        if connection.scalar(select(model.name).where(model.id == row_id)) != case.marker + "-" + (
                "staff" if name == "staff" else "service"):
            raise RuntimeError("Synthetic catalog ownership mismatch")
    rule_id = next(iter(case.ids["rules"]))
    if connection.scalar(select(CommissionRule.name).where(CommissionRule.id == rule_id)) != case.marker + "-rule":
        raise RuntimeError("Synthetic rule ownership mismatch")


def _cleanup(case):
    try:
        with case.engine.begin() as connection:
            _owned_ids(case, connection)
            for name in ("items", "claims", "attempts", "transactions", "audits",
                         "services", "staff", "rules", "users"):
                if name == "users" and case.operating_dates:
                    connection.execute(delete(OperatingDay).where(
                        OperatingDay.business_date.in_(case.operating_dates)))
                if case.ids[name]:
                    model = MODELS[name]
                    connection.execute(delete(model).where(model.id.in_(case.ids[name])))
        with case.engine.connect() as verifier:
            _connected_target(verifier, case.url)
            if case.operating_dates and verifier.scalar(select(func.count()).select_from(OperatingDay).where(
                    OperatingDay.business_date.in_(case.operating_dates))) != 0:
                raise RuntimeError("Synthetic operating date remains")
            for name, model in MODELS.items():
                if case.ids[name] and verifier.scalar(select(func.count()).select_from(model).where(
                        model.id.in_(case.ids[name]))) != 0:
                    raise RuntimeError("Synthetic row remains: " + name)
    except Exception as exc:
        raise AssertionError(f"Synthetic cleanup failed: run={case.marker}, ids={case.ids}") from exc


@pytest.fixture
def case():
    # Ordinary pytest skips before reading .env or opening a PostgreSQL connection.
    if os.getenv("RUN_SALE_ATTEMPT_CONCURRENCY_TESTS") != "1":
        pytest.skip("Set RUN_SALE_ATTEMPT_CONCURRENCY_TESTS=1 for controlled real-commit tests")
    url = get_database_url()
    _configured_target(url)
    engine = create_engine(url, pool_size=5, max_overflow=0, pool_pre_ping=True,
                           connect_args={"connect_timeout": 5,
                                         "options": "-c statement_timeout=15000 -c lock_timeout=3000"})
    current = Case(engine, url, PREFIX + uuid4().hex)
    setup_committed = False
    try:
        with engine.connect() as connection:
            _connected_target(connection, url)
            if connection.scalar(select(func.count()).select_from(User).where(User.username.like(PREFIX + "%"))):
                pytest.fail("Previous synthetic attempt-race user remains; no writes attempted")
        with engine.begin() as connection:
            _connected_target(connection, url)
            for suffix, role, attribute in (
                ("-owner", "Owner", "owner_id"),
                ("-second-owner", "Owner", "second_owner_id"),
                ("-cashier", "Cashier", "cashier_id"),
            ):
                row_id = connection.execute(insert(User).values(
                    username=current.marker + suffix, password_hash="synthetic-no-login",
                    role=role, active=True,
                ).returning(User.id)).scalar_one()
                setattr(current, attribute, row_id)
                current.ids["users"].add(row_id)
            current.staff_id = connection.execute(insert(Staff).values(
                name=current.marker + "-staff", role="Stylist", active=True,
            ).returning(Staff.id)).scalar_one()
            current.ids["staff"].add(current.staff_id)
            rule_id = connection.execute(insert(CommissionRule).values(
                name=current.marker + "-rule", type="Percentage", value=Decimal("50.00"),
                active=True,
            ).returning(CommissionRule.id)).scalar_one()
            current.ids["rules"].add(rule_id)
            current.service_id = connection.execute(insert(Service).values(
                name=current.marker + "-service", current_price=Decimal("101.00"),
                commission_rule_id=rule_id, active=True,
            ).returning(Service.id)).scalar_one()
            current.ids["services"].add(current.service_id)
        setup_committed = True
        yield current
    finally:
        try:
            if setup_committed:
                _cleanup(current)
        finally:
            engine.dispose()


def _reserve(case, request, user_id, role, key):
    with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            return reserve_sale_attempt(session, request, actor_user_id=user_id,
                                        role=role, idempotency_key=key)


def _write(case, request, user_id, key):
    with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            if request.source == "Direct":
                return record_direct_sale(session, request.sale, actor_user_id=user_id,
                                          idempotency_key=key, enforce_reservation=True)
            return record_manual_sale(session, request.sale, actor_user_id=user_id,
                                      role="Owner", idempotency_key=key, enforce_reservation=True)


def _cancel(case, attempt_id):
    with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            return cancel_sale_attempt(session, attempt_id=attempt_id,
                                       actor_user_id=case.owner_id, role="Owner",
                                       request=CancellationRequest(reason="Synthetic evidence reviewed",
                                                                   evidence_verified=True))


def _wait_for_lock(case, pid):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with case.engine.connect() as observer:
            _connected_target(observer, case.url)
            if observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid=:pid"),
                               {"pid": pid}) is True:
                return
        time.sleep(0.05)
    raise AssertionError("Second connection did not wait on the expected lock")


def test_competing_reservations_and_same_key_replay(case):
    request = case.direct()
    keys = (uuid4(), uuid4())
    gate = threading.Barrier(2)
    pids = set()
    guard = threading.Lock()

    def compete(key):
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            with guard:
                pids.add(pid)
            gate.wait(timeout=8)
            try:
                with session.begin_nested():
                    attempt, replay = reserve_sale_attempt(session, request,
                                                           actor_user_id=case.cashier_id,
                                                           role="Cashier", idempotency_key=key)
                session.commit()
                return attempt, replay, None
            except ApiError as exc:
                session.rollback()
                return None, None, exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in
                   (pool.submit(compete, keys[0]), pool.submit(compete, keys[1]))]
    assert len(pids) == 2
    assert sorted(result[2] or "created" for result in results) == ["created", "open_sale_attempt"]
    winner = next(result[0] for result in results if result[0] is not None)
    replay, repeated = _reserve(case, request, case.cashier_id, "Cashier", winner.idempotency_key)
    assert repeated and replay.id == winner.id and replay.direct_reference == winner.direct_reference
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleAttempt).where(
            SaleAttempt.user_id == case.cashier_id)) == 1


def test_simultaneous_same_key_reservations_replay_one_attempt(case):
    request, key = case.direct(), uuid4()
    gate = threading.Barrier(2)
    pids = set()
    guard = threading.Lock()

    def reserve_once():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            with guard:
                pids.add(pid)
            gate.wait(timeout=8)
            with session.begin_nested():
                result = reserve_sale_attempt(session, request, actor_user_id=case.cashier_id,
                                              role="Cashier", idempotency_key=key)
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in
                   (pool.submit(reserve_once), pool.submit(reserve_once))]
    assert len(pids) == 2
    assert sorted(replayed for _, replayed in results) == [False, True]
    assert results[0][0].id == results[1][0].id
    assert results[0][0].direct_reference == results[1][0].direct_reference
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleAttempt).where(
            SaleAttempt.user_id == case.cashier_id)) == 1


def test_writer_first_beats_owner_cancellation(case):
    request, key = case.direct(), uuid4()
    attempt, _ = _reserve(case, request, case.cashier_id, "Cashier", key)
    written = threading.Event()
    release = threading.Event()
    cancel_started = threading.Event()
    cancel_pid = []

    def writer():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                sale, replay = record_direct_sale(session, request.sale,
                                                  actor_user_id=case.cashier_id,
                                                  idempotency_key=key, enforce_reservation=True)
                assert not replay
                written.set()
                assert release.wait(timeout=8)
            return sale

    def canceller():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            cancel_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            cancel_started.set()
            with session.begin_nested():
                result = cancel_sale_attempt(session, attempt_id=attempt.id,
                                             actor_user_id=case.owner_id, role="Owner",
                                             request=CancellationRequest(reason="Synthetic review",
                                                                         evidence_verified=True))
            session.commit()
            return result

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            sale_future = pool.submit(writer)
            if not written.wait(timeout=8):
                if sale_future.done():
                    sale_future.result()  # Surface the writer exception instead of masking it.
                raise AssertionError("Writer did not reach the pre-commit gate")
            cancel_future = pool.submit(canceller)
            assert cancel_started.wait(timeout=8)
            _wait_for_lock(case, cancel_pid[0])
            release.set()
            sale = sale_future.result(timeout=20)
            cancelled, error = cancel_future.result(timeout=20)
    finally:
        release.set()
    assert cancelled is None and error.status_code == 409
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(SaleAttempt.state).where(SaleAttempt.id == attempt.id)) == "Committed"
        assert verifier.scalar(select(SaleAttempt.transaction_id).where(SaleAttempt.id == attempt.id)) == sale.id
        assert verifier.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.actor_user_id == case.owner_id,
            AuditEvent.event_type == "SaleAttemptCancellation",
            AuditEvent.outcome == "Failure")) == 1


def test_cancellation_first_fences_delayed_post_before_key_lock(case):
    request, key = case.direct(), uuid4()
    attempt, _ = _reserve(case, request, case.cashier_id, "Cashier", key)
    ready = threading.Event()
    release = threading.Event()

    def delayed_writer():
        ready.set()  # Intentionally delayed before record_direct_sale takes the key lock.
        assert release.wait(timeout=8)
        with pytest.raises(ApiError) as error:
            _write(case, request, case.cashier_id, key)
        return error.value.code

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(delayed_writer)
            assert ready.wait(timeout=8)
            cancelled, error = _cancel(case, attempt.id)
            assert error is None and cancelled.state == "Cancelled"
            release.set()
            assert future.result(timeout=20) == "attempt_cancelled"
    finally:
        release.set()
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.cashier_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.cashier_id)) == 0
        assert verifier.scalar(select(SaleAttempt.state).where(SaleAttempt.id == attempt.id)) == "Cancelled"


def test_manual_reference_race_across_users(case):
    request = case.manual()
    reference = request.sale.manual_reference
    gate = threading.Barrier(2)

    def compete(user_id):
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            session.scalar(text("SELECT pg_backend_pid()"))
            gate.wait(timeout=8)
            try:
                with session.begin_nested():
                    attempt, replay = reserve_sale_attempt(session, request, actor_user_id=user_id,
                                                           role="Owner", idempotency_key=uuid4())
                session.commit()
                assert not replay
                return attempt, None
            except ApiError as exc:
                session.rollback()
                return None, exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in
                   (pool.submit(compete, case.owner_id), pool.submit(compete, case.second_owner_id))]
    assert sorted(error or "created" for _, error in results) == ["created", "duplicate_paper_reference"]
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleAttempt).where(
            SaleAttempt.manual_reference == reference)) == 1


def test_committed_exact_key_replay_and_cross_connection_visibility(case):
    direct, direct_key = case.direct(), uuid4()
    direct_attempt, _ = _reserve(case, direct, case.cashier_id, "Cashier", direct_key)
    first, replay = _write(case, direct, case.cashier_id, direct_key)
    assert not replay
    again, replay = _write(case, direct, case.cashier_id, direct_key)
    assert replay and again.id == first.id

    manual, manual_key = case.manual(), uuid4()
    manual_attempt, _ = _reserve(case, manual, case.owner_id, "Owner", manual_key)
    manual_sale, replay = _write(case, manual, case.owner_id, manual_key)
    assert not replay
    manual_again, replay = _write(case, manual, case.owner_id, manual_key)
    assert replay and manual_again.id == manual_sale.id
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id.in_((case.cashier_id, case.owner_id)))) == 2
        assert verifier.scalar(select(func.count()).select_from(TransactionItem).where(
            TransactionItem.transaction_id.in_((first.id, manual_sale.id)))) == 2
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id.in_((case.cashier_id, case.owner_id)))) == 2
        assert verifier.scalar(select(SaleAttempt.transaction_id).where(
            SaleAttempt.id == direct_attempt.id)) == first.id
        assert verifier.scalar(select(SaleAttempt.transaction_id).where(
            SaleAttempt.id == manual_attempt.id)) == manual_sale.id
        assert verifier.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.actor_user_id == case.owner_id,
            AuditEvent.event_type == "ManualSaleCreated", AuditEvent.outcome == "Success")) == 1


def test_failed_write_and_audit_rollback_leave_reserved_fence(case):
    bad, key = case.direct("99.00"), uuid4()
    attempt, _ = _reserve(case, bad, case.cashier_id, "Cashier", key)
    with pytest.raises(ApiError) as error:
        _write(case, bad, case.cashier_id, key)
    assert error.value.status_code == 422
    with patch("app.modules.transactions.attempt_service._audit_cancellation", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            _cancel(case, attempt.id)
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(SaleAttempt.state).where(SaleAttempt.id == attempt.id)) == "Reserved"
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.cashier_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.cashier_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.actor_user_id == case.owner_id,
            AuditEvent.event_type == "SaleAttemptCancellation")) == 0


def _business_date(case, request):
    if request.source == "Manual":
        return request.sale.date_time.astimezone(ZoneInfo("Asia/Manila")).date()
    with case.engine.connect() as connection:
        _connected_target(connection, case.url)
        return connection.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Manila')::date"))


def _calendar_change(case, day, status, expected_version):
    with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            return update_day(session, business_date=day,
                              payload=OperatingDayUpdate(
                                  status=status, expected_version=expected_version,
                                  closure_reason="Synthetic closure" if status == "Closed" else None),
                              actor_user_id=case.owner_id)


def _legacy_write(case, request, key):
    with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            if request.source == "Direct":
                return record_direct_sale(session, request.sale, actor_user_id=case.owner_id,
                                          idempotency_key=key)
            return record_manual_sale(session, request.sale, actor_user_id=case.owner_id,
                                      role="Owner", idempotency_key=key)


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_closed_rejection_claim_rollback_and_replay_after_correction(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day, key = _business_date(case, request), uuid4()
    assert _calendar_change(case, day, "Closed", 0).status == "Closed"
    with pytest.raises(ApiError) as error:
        _legacy_write(case, request, key)
    assert (error.value.status_code, error.value.code) == (409, "business_date_closed")
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.owner_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.owner_id)) == 0
    assert _calendar_change(case, day, "Unknown", 1).version == 2
    sale, replay = _legacy_write(case, request, key)
    assert not replay and sale.business_date == day
    assert _calendar_change(case, day, "Open", 2).version == 3
    again, replay = _legacy_write(case, request, key)
    assert replay and again.id == sale.id


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_unconfirmed_planned_closure_allows_sale_without_promotion(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day = _business_date(case, request)
    # Simulate a future plan that reached its date without Owner confirmation.
    with case.engine.begin() as connection:
        _connected_target(connection, case.url)
        if connection.scalar(select(OperatingDay.business_date).where(
                OperatingDay.business_date == day)) is not None:
            pytest.fail("Unexpected operating date on isolated test target")
        connection.execute(insert(OperatingDay).values(
            business_date=day, status="PlannedClosed", closure_reason="Synthetic unconfirmed plan",
            created_by_user_id=case.owner_id, updated_by_user_id=case.owner_id, version=1))
    sale, replay = _legacy_write(case, request, uuid4())
    assert not replay and sale.business_date == day
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(OperatingDay.status).where(
            OperatingDay.business_date == day)) == "PlannedClosed"


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_sale_commit_prevents_concurrent_closed_update(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day = _business_date(case, request)
    key = uuid4()
    sale_ready, release_sale, closure_started = (threading.Event() for _ in range(3))
    closure_pid = []

    def sale_first():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                if source == "Direct":
                    sale, _ = record_direct_sale(session, request.sale,
                                                 actor_user_id=case.owner_id, idempotency_key=key)
                else:
                    sale, _ = record_manual_sale(session, request.sale,
                                                 actor_user_id=case.owner_id, role="Owner",
                                                 idempotency_key=key)
                sale_ready.set()
                assert release_sale.wait(timeout=8)
                return sale.id

    def close_second():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            closure_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            closure_started.set()
            try:
                with session.begin_nested():
                    update_day(session, business_date=day,
                               payload=OperatingDayUpdate(status="Closed", closure_reason="Race",
                                                          expected_version=0),
                               actor_user_id=case.owner_id)
                session.commit()
                return "closed"
            except ApiError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        sale_future = pool.submit(sale_first)
        try:
            assert sale_ready.wait(timeout=8)
            close_future = pool.submit(close_second)
            assert closure_started.wait(timeout=8)
            _wait_for_lock(case, closure_pid[0])
        finally:
            release_sale.set()
        sale_id = sale_future.result(timeout=15)
        assert close_future.result(timeout=15) == "completed_sales_on_date"
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(Transaction.id).where(Transaction.id == sale_id)) == sale_id
        assert verifier.scalar(select(OperatingDay.business_date).where(
            OperatingDay.business_date == day)) is None


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_closed_update_commit_prevents_concurrent_sale(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day, key = _business_date(case, request), uuid4()
    closure_ready, release_closure, sale_started = (threading.Event() for _ in range(3))
    sale_pid = []

    def close_first():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                update_day(session, business_date=day,
                           payload=OperatingDayUpdate(status="Closed", closure_reason="Race",
                                                      expected_version=0),
                           actor_user_id=case.owner_id)
                closure_ready.set()
                assert release_closure.wait(timeout=8)

    def sale_second():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            sale_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            sale_started.set()
            try:
                with session.begin_nested():
                    if source == "Direct":
                        record_direct_sale(session, request.sale, actor_user_id=case.owner_id,
                                           idempotency_key=key)
                    else:
                        record_manual_sale(session, request.sale, actor_user_id=case.owner_id,
                                           role="Owner", idempotency_key=key)
                session.commit()
                return "created"
            except ApiError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        closure_future = pool.submit(close_first)
        try:
            assert closure_ready.wait(timeout=8)
            sale_future = pool.submit(sale_second)
            assert sale_started.wait(timeout=8)
            _wait_for_lock(case, sale_pid[0])
        finally:
            release_closure.set()
        closure_future.result(timeout=15)
        assert sale_future.result(timeout=15) == "business_date_closed"
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.owner_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.owner_id)) == 0
        assert verifier.scalar(select(OperatingDay.status).where(
            OperatingDay.business_date == day)) == "Closed"


def test_concurrent_calendar_corrections_reject_stale_version(case):
    day = _business_date(case, case.direct())
    second_started, second_pid = threading.Event(), []

    def stale_correction():
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            second_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
            second_started.set()
            try:
                with session.begin_nested():
                    update_day(session, business_date=day,
                               payload=OperatingDayUpdate(status="Closed", closure_reason="Stale",
                                                          expected_version=0),
                               actor_user_id=case.second_owner_id)
                session.commit()
                return "changed"
            except ApiError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(case.engine, autoflush=False, expire_on_commit=False) as first:
            with first.begin():
                update_day(first, business_date=day,
                           payload=OperatingDayUpdate(status="Open", expected_version=0),
                           actor_user_id=case.owner_id)
                future = pool.submit(stale_correction)
                assert second_started.wait(timeout=8)
                _wait_for_lock(case, second_pid[0])
        assert future.result(timeout=15) == "operating_day_changed"
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(OperatingDay.status).where(
            OperatingDay.business_date == day)) == "Open"
        assert verifier.scalar(select(OperatingDay.version).where(
            OperatingDay.business_date == day)) == 1


def test_bulk_open_locks_dates_in_ascending_order(case):
    today = _business_date(case, case.direct())
    dates = (today - timedelta(days=1), today - timedelta(days=2))
    payload = BulkOpenVerification.model_validate({"dates": [
        {"business_date": day.isoformat(), "expected_version": 0} for day in dates]})
    acquired = []

    def record_lock(session, day):
        acquired.append(day)
        lock_operating_date(session, day)

    with patch("app.modules.operating_days.service.lock_operating_date", side_effect=record_lock):
        with Session(case.engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                result = bulk_verify_open(session, payload=payload, actor_user_id=case.owner_id)
    assert acquired == sorted(dates)
    assert result.changed_count == 2
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert list(verifier.scalars(select(OperatingDay.status).where(
            OperatingDay.business_date.in_(dates)))) == ["Open", "Open"]


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_reserved_attempt_survives_closed_rejection(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day, key = _business_date(case, request), uuid4()
    attempt, _ = _reserve(case, request, case.owner_id, "Owner", key)
    _calendar_change(case, day, "Closed", 0)
    with pytest.raises(ApiError) as error:
        _write(case, request, case.owner_id, key)
    assert error.value.code == "business_date_closed"
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(SaleAttempt.state).where(SaleAttempt.id == attempt.id)) == "Reserved"
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.owner_id)) == 0
    _calendar_change(case, day, "Open", 1)
    sale, replay = _write(case, request, case.owner_id, key)
    assert not replay and sale.business_date == day
    again, replay = _write(case, request, case.owner_id, key)
    assert replay and again.id == sale.id


def test_direct_manila_midnight_rolls_back_on_real_postgres(case):
    request, key = case.direct(), uuid4()
    day = _business_date(case, request)
    before = datetime.combine(day, clock_time(23, 59, 59), ZoneInfo("Asia/Manila")).astimezone(timezone.utc)
    clock = iter((before - timedelta(minutes=1), before, before + timedelta(seconds=1)))
    with patch("app.modules.transactions.service._database_time", side_effect=lambda _session: next(clock)):
        with pytest.raises(ApiError) as error:
            _legacy_write(case, request, key)
    assert (error.value.status_code, error.value.code) == (503, "sale_outcome_uncertain")
    with case.engine.connect() as verifier:
        _connected_target(verifier, case.url)
        assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.owner_id)) == 0
        assert verifier.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.owner_id)) == 0


@pytest.mark.parametrize("source", ["Direct", "Manual"])
def test_sale_date_lock_timeout_rolls_back_claim_then_same_key_retries(case, source):
    request = case.direct() if source == "Direct" else case.manual()
    day, key = _business_date(case, request), uuid4()
    with Session(case.engine, autoflush=False, expire_on_commit=False) as holder:
        with holder.begin():
            lock_operating_date(holder, day)
            with pytest.raises(ApiError) as error:
                _legacy_write(case, request, key)
            assert (error.value.status_code, error.value.code) == (503, "sale_outcome_uncertain")
            with case.engine.connect() as verifier:
                _connected_target(verifier, case.url)
                assert verifier.scalar(select(func.count()).select_from(SaleIdempotency).where(
                    SaleIdempotency.user_id == case.owner_id)) == 0
                assert verifier.scalar(select(func.count()).select_from(Transaction).where(
                    Transaction.recorded_by_user_id == case.owner_id)) == 0
    sale, replay = _legacy_write(case, request, key)
    assert not replay and sale.business_date == day
