"""Opt-in B2 writer checks: temporary migration and all synthetic rows roll back."""

import os
from datetime import timedelta
from decimal import Decimal
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import ApiError
from app.db.model_registry import get_model_metadata
from app.modules.audit.models import AuditEvent
from app.modules.transactions.attempt_models import SaleAttempt
from app.modules.transactions.attempt_schemas import CancellationRequest, DirectReservation, ManualReservation
from app.modules.transactions.attempt_service import cancel_sale_attempt, reserve_sale_attempt
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.manual_service import record_manual_sale
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.schemas import ManualSaleCreate, SaleCreate
from app.modules.transactions.service import record_direct_sale


REVISION = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))).get_revision("20261027_01").module


def _preflight(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured target")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if (address is None or not ip_address(str(address)).is_loopback
            or connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"
            or connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1):
        raise RuntimeError("Unsafe connected target or revision")
    revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
    exists = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
    if (revision, exists) not in (("20261020_01", False), ("20261027_01", True)):
        raise RuntimeError("Unexpected schema revision or sale_attempts state")
    return exists


def _direct(service_id, staff_id, price="101.00"):
    return SaleCreate.model_validate({"payment_method": "Cash", "items": [
        {"service_id": service_id, "staff_id": staff_id, "selling_price": price},
    ]})


def _manual(service_id, staff_id, occurred, reference, price="101.00", percentage="50.00"):
    return ManualSaleCreate.model_validate({
        "date_time": occurred.isoformat(), "manual_reference": reference,
        "verified_against_paper": True, "payment_method": "Cash", "items": [
            {"service_id": service_id, "staff_id": staff_id, "selling_price": price,
             "item_name_snapshot": "Paper haircut", "commission_type_snapshot": "Percentage",
             "commission_value_snapshot": percentage},
        ],
    })


def test_reservation_aware_direct_and_manual_writes_are_atomic():
    if os.getenv("RUN_SALE_ATTEMPT_WRITER_TESTS") != "1":
        pytest.skip("Set RUN_SALE_ATTEMPT_WRITER_TESTS=1 for rollback-only yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured target; no connection attempted")
    engine = sa.create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            migrated = _preflight(connection, url)
            get_model_metadata()
            before = tuple(connection.scalar(text(f"SELECT count(*) FROM {name}")) for name in (
                "transactions", "transaction_items", "sale_idempotency", "audit_events"))
            scope = connection.begin_nested()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '3s'"))
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                if not migrated:
                    with Operations.context(MigrationContext.configure(connection)):
                        REVISION.upgrade()
                marker = "synthetic-b2-" + uuid4().hex
                user_id = connection.scalar(text(
                    "INSERT INTO users (username,password_hash,role) VALUES (:name,'synthetic-unused','Owner') RETURNING id"
                ), {"name": marker})
                staff_id = connection.scalar(text(
                    "INSERT INTO staff (name,role) VALUES (:name,'Stylist') RETURNING id"
                ), {"name": marker})
                rule_id = connection.scalar(text(
                    "INSERT INTO commission_rules (name,type,value) "
                    "VALUES (:name,'Percentage',50.00) RETURNING id"
                ), {"name": marker})
                service_id = connection.scalar(text(
                    "INSERT INTO services (name,current_price,commission_rule_id) "
                    "VALUES (:name,101.00,:rule_id) RETURNING id"
                ), {"name": marker, "rule_id": rule_id})
                session = Session(bind=connection, autoflush=False, expire_on_commit=False,
                                  join_transaction_mode="create_savepoint")
                try:
                    direct = _direct(service_id, staff_id)
                    key = uuid4()
                    with pytest.raises(ApiError) as error:
                        record_direct_sale(session, direct, actor_user_id=user_id,
                                           idempotency_key=key, enforce_reservation=True)
                    assert error.value.code == "reservation_required"
                    reserved, _ = reserve_sale_attempt(session, DirectReservation(source="Direct", sale=direct),
                                                       actor_user_id=user_id, role="Owner", idempotency_key=key)
                    sale, replay = record_direct_sale(session, direct, actor_user_id=user_id,
                                                      idempotency_key=key, enforce_reservation=True)
                    assert not replay and sale.total_staff_commission == Decimal("51.00")
                    assert connection.scalar(text("SHOW lock_timeout")) == "3s"
                    assert connection.scalar(text("SHOW statement_timeout")) == "15s"
                    assert session.get(SaleAttempt, reserved.id).state == "Committed"
                    assert session.get(SaleAttempt, reserved.id).transaction_id == sale.id
                    same, replay = record_direct_sale(session, direct, actor_user_id=user_id,
                                                      idempotency_key=key, enforce_reservation=True)
                    assert replay and same.id == sale.id
                    with pytest.raises(ApiError) as error:
                        record_direct_sale(session, _direct(service_id, staff_id, "102.00"),
                                           actor_user_id=user_id, idempotency_key=key,
                                           enforce_reservation=True)
                    assert error.value.status_code == 409
                    session.expire_all()

                    # Legacy committed exact-key replay has no fabricated attempt.
                    legacy_key = uuid4()
                    legacy, _ = record_direct_sale(session, direct, actor_user_id=user_id,
                                                   idempotency_key=legacy_key)
                    legacy_replay, replay = record_direct_sale(session, direct, actor_user_id=user_id,
                                                               idempotency_key=legacy_key,
                                                               enforce_reservation=True)
                    assert replay and legacy_replay.id == legacy.id
                    assert session.scalar(select(SaleAttempt.id).where(
                        SaleAttempt.idempotency_key == legacy_key)) is None

                    occurred = connection.scalar(text("SELECT clock_timestamp()")) - timedelta(minutes=1)
                    prefix = "PAPER-" + occurred.astimezone(ZoneInfo("Asia/Manila")).strftime("%Y%m%d")
                    legacy_manual = _manual(service_id, staff_id, occurred, prefix + "-001")
                    legacy_manual_key = uuid4()
                    legacy_manual_sale, _ = record_manual_sale(session, legacy_manual,
                                                                actor_user_id=user_id, role="Owner",
                                                                idempotency_key=legacy_manual_key)
                    legacy_manual_replay, replay = record_manual_sale(
                        session, legacy_manual, actor_user_id=user_id, role="Owner",
                        idempotency_key=legacy_manual_key, enforce_reservation=True)
                    assert replay and legacy_manual_replay.id == legacy_manual_sale.id
                    transaction = session.get(Transaction, legacy_manual_sale.id)
                    transaction.status = "Voided"
                    transaction.void_reason = "synthetic correction"
                    transaction.voided_by_user_id = user_id
                    transaction.voided_at = connection.scalar(text("SELECT clock_timestamp()"))
                    session.flush()
                    with pytest.raises(ApiError) as error:
                        reserve_sale_attempt(session, ManualReservation(source="Manual", sale=legacy_manual),
                                             actor_user_id=user_id, role="Owner", idempotency_key=uuid4())
                    assert error.value.code == "duplicate_paper_reference"

                    manual = _manual(service_id, staff_id, occurred, prefix + "-002")
                    manual_key = uuid4()
                    with pytest.raises(ApiError) as error:
                        record_manual_sale(session, manual, actor_user_id=user_id, role="Owner",
                                           idempotency_key=manual_key, enforce_reservation=True)
                    assert error.value.code == "reservation_required"
                    reserved_manual, _ = reserve_sale_attempt(session, ManualReservation(source="Manual", sale=manual),
                                                              actor_user_id=user_id, role="Owner",
                                                              idempotency_key=manual_key)
                    manual_sale, replay = record_manual_sale(session, manual, actor_user_id=user_id,
                                                             role="Owner", idempotency_key=manual_key,
                                                             enforce_reservation=True)
                    assert not replay and session.get(SaleAttempt, reserved_manual.id).state == "Committed"
                    assert session.scalar(select(sa.func.count()).select_from(AuditEvent).where(
                        AuditEvent.event_type == "ManualSaleCreated",
                        AuditEvent.resource_id == str(manual_sale.id))) == 1
                    manual_replay, replay = record_manual_sale(session, manual, actor_user_id=user_id,
                                                               role="Owner", idempotency_key=manual_key,
                                                               enforce_reservation=True)
                    assert replay and manual_replay.id == manual_sale.id
                    with pytest.raises(ApiError) as error:
                        record_manual_sale(session, _manual(service_id, staff_id, occurred, prefix + "-002", "102.00"),
                                           actor_user_id=user_id, role="Owner", idempotency_key=manual_key,
                                           enforce_reservation=True)
                    assert error.value.status_code == 409

                    bad_manual = _manual(service_id, staff_id, occurred, prefix + "-003", "0.51", "100.00")
                    bad_manual_key = uuid4()
                    bad_attempt, _ = reserve_sale_attempt(session, ManualReservation(source="Manual", sale=bad_manual),
                                                          actor_user_id=user_id, role="Owner",
                                                          idempotency_key=bad_manual_key)
                    manual_savepoint = session.begin_nested()
                    try:
                        with pytest.raises(ApiError) as error:
                            record_manual_sale(session, bad_manual, actor_user_id=user_id, role="Owner",
                                               idempotency_key=bad_manual_key, enforce_reservation=True)
                        assert error.value.status_code == 422
                    finally:
                        manual_savepoint.rollback()
                        session.expire_all()
                    assert session.get(SaleAttempt, bad_attempt.id).state == "Reserved"
                    assert session.scalar(select(SaleIdempotency.id).where(
                        SaleIdempotency.user_id == user_id,
                        SaleIdempotency.idempotency_key == str(bad_manual_key))) is None
                    assert session.scalar(select(Transaction.id).where(
                        Transaction.manual_reference == prefix + "-003")) is None
                    _, error = cancel_sale_attempt(session, attempt_id=bad_attempt.id,
                                                   actor_user_id=user_id, role="Owner",
                                                   request=CancellationRequest(
                                                       reason="Synthetic evidence reviewed", evidence_verified=True))
                    assert error is None

                    failed_payload = _direct(service_id, staff_id, "99.00")
                    failed_key = uuid4()
                    failed, _ = reserve_sale_attempt(session, DirectReservation(source="Direct", sale=failed_payload),
                                                     actor_user_id=user_id, role="Owner", idempotency_key=failed_key)
                    savepoint = session.begin_nested()
                    try:
                        with pytest.raises(ApiError) as error:
                            record_direct_sale(session, failed_payload, actor_user_id=user_id,
                                               idempotency_key=failed_key, enforce_reservation=True)
                        assert error.value.status_code == 422
                    finally:
                        savepoint.rollback()
                        session.expire_all()
                    assert session.get(SaleAttempt, failed.id).state == "Reserved"
                    assert session.scalar(select(SaleIdempotency.id).where(
                        SaleIdempotency.user_id == user_id,
                        SaleIdempotency.idempotency_key == str(failed_key))) is None
                    assert session.scalar(select(sa.func.count()).select_from(TransactionItem).where(
                        TransactionItem.transaction_id == sale.id)) == 1
                    cancelled, error = cancel_sale_attempt(session, attempt_id=failed.id,
                                                           actor_user_id=user_id, role="Owner",
                                                           request=CancellationRequest(
                                                               reason="Synthetic evidence reviewed", evidence_verified=True))
                    assert error is None and cancelled.state == "Cancelled"
                    with pytest.raises(ApiError) as error:
                        record_direct_sale(session, failed_payload, actor_user_id=user_id,
                                           idempotency_key=failed_key, enforce_reservation=True)
                    assert error.value.code == "attempt_cancelled"
                finally:
                    session.close()
            finally:
                scope.rollback()
                connection.rollback()
        with engine.connect() as verifier:
            _preflight(verifier, url)
            assert tuple(verifier.scalar(text(f"SELECT count(*) FROM {name}")) for name in (
                "transactions", "transaction_items", "sale_idempotency", "audit_events")) == before
    finally:
        engine.dispose()
