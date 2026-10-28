"""Opt-in B1 service tests: temporary migration and synthetic rows always roll back."""

import os
from datetime import timedelta
from ipaddress import ip_address
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import ApiError
from app.db.model_registry import get_model_metadata
from app.modules.audit.models import AuditEvent
from app.modules.transactions.attempt_models import SaleAttempt
from app.modules.transactions.attempt_schemas import AttemptInvestigation, CancellationRequest, ReservationRequest
from app.modules.transactions.attempt_service import (
    cancel_sale_attempt, get_own_attempt_by_key, get_own_open_attempt,
    investigate_attempts, reserve_sale_attempt,
)


REVISION = ScriptDirectory.from_config(Config(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "alembic.ini"))).get_revision("20261027_01").module


def _preflight(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured database")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if (connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"
            or address is None or not ip_address(str(address)).is_loopback):
        raise RuntimeError("Unsafe connected database")
    revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
    exists = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
    if (connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1
            or (revision, exists) not in (("20261020_01", False), ("20261027_01", True))):
        raise RuntimeError("Unexpected schema revision or sale_attempts state")
    return exists


def _direct(price="100.00"):
    return TypeAdapter(ReservationRequest).validate_python({
        "source": "Direct", "sale": {"payment_method": "Cash", "items": [
            {"service_id": 1, "staff_id": 1, "selling_price": price},
        ]},
    })


def _manual(reference, occurred):
    return TypeAdapter(ReservationRequest).validate_python({
        "source": "Manual", "sale": {
            "date_time": occurred.isoformat(), "manual_reference": reference,
            "verified_against_paper": True, "payment_method": "Cash", "items": [
                {"service_id": 1, "staff_id": 1, "selling_price": "100.00",
                 "item_name_snapshot": "Historical haircut", "commission_type_snapshot": "Percentage",
                 "commission_value_snapshot": "50.00"},
            ],
        },
    })


def test_internal_reservation_discovery_cancellation_and_rollback():
    if os.getenv("RUN_SALE_ATTEMPT_SERVICE_TESTS") != "1":
        pytest.skip("Set RUN_SALE_ATTEMPT_SERVICE_TESTS=1 for rollback-only yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured database; no connection attempted")
    engine = sa.create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            migrated = _preflight(connection, url)
            get_model_metadata()
            legacy_before = (
                connection.scalar(text("SELECT count(*) FROM transactions")),
                connection.scalar(text("SELECT count(*) FROM sale_idempotency")),
            )
            scope = connection.begin_nested()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '3s'"))
                connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                if not migrated:
                    with Operations.context(MigrationContext.configure(connection)):
                        REVISION.upgrade()
                marker = "synthetic-b1-" + uuid4().hex
                owner_id = connection.scalar(text(
                    "INSERT INTO users (username,password_hash,role) VALUES (:name,'synthetic-unused','Owner') RETURNING id"
                ), {"name": marker + "-owner"})
                cashier_id = connection.scalar(text(
                    "INSERT INTO users (username,password_hash,role) VALUES (:name,'synthetic-unused','Cashier') RETURNING id"
                ), {"name": marker + "-cashier"})
                session = Session(bind=connection, autoflush=False, expire_on_commit=False,
                                  join_transaction_mode="create_savepoint")
                try:
                    key = uuid4()
                    direct, retry = reserve_sale_attempt(session, _direct(), actor_user_id=cashier_id,
                                                         role="Cashier", idempotency_key=key)
                    session.flush()
                    assert retry is False and direct.direct_reference == f"DS-{direct.id:012d}"
                    assert "request_hash" not in type(direct).model_fields
                    assert get_own_open_attempt(session, actor_user_id=cashier_id, role="Cashier").id == direct.id
                    assert get_own_attempt_by_key(session, actor_user_id=cashier_id, role="Cashier",
                                                  idempotency_key=key).id == direct.id
                    with pytest.raises(ApiError) as error:
                        get_own_attempt_by_key(session, actor_user_id=owner_id, role="Owner",
                                               idempotency_key=key)
                    assert error.value.status_code == 404
                    assert get_own_open_attempt(session, actor_user_id=owner_id, role="Owner") is None
                    session.flush()
                    same, retry = reserve_sale_attempt(session, _direct(), actor_user_id=cashier_id,
                                                       role="Cashier", idempotency_key=key)
                    session.flush()
                    assert retry is True and same.id == direct.id
                    for candidate_key, payload, expected in (
                        (key, _direct("101.00"), "idempotency_conflict"),
                        (uuid4(), _direct(), "open_sale_attempt"),
                    ):
                        with pytest.raises(ApiError) as error:
                            reserve_sale_attempt(session, payload, actor_user_id=cashier_id,
                                                 role="Cashier", idempotency_key=candidate_key)
                        assert error.value.code == expected
                        session.expire_all()

                    assert investigate_attempts(session, role="Owner", query=AttemptInvestigation(
                        recording_user_id=cashier_id, reference=direct.direct_reference,
                    ))[0].id == direct.id
                    assert investigate_attempts(session, role="Owner", query=AttemptInvestigation(
                        recording_user_id=owner_id,
                    )) == []
                    with pytest.raises(ApiError) as error:
                        investigate_attempts(session, role="Cashier", query=AttemptInvestigation(
                            recording_user_id=owner_id,
                        ))
                    assert error.value.status_code == 403
                    session.expire_all()

                    cancel = CancellationRequest(reason="External evidence verified", evidence_verified=True)
                    result, error = cancel_sale_attempt(session, attempt_id=direct.id,
                                                        actor_user_id=cashier_id, role="Cashier", request=cancel)
                    session.flush()
                    assert result is None and error.status_code == 403
                    assert session.get(SaleAttempt, direct.id).state == "Reserved"
                    session.expire_all()

                    result, error = cancel_sale_attempt(session, attempt_id=direct.id,
                                                        actor_user_id=owner_id, role="Owner", request=cancel)
                    session.flush()
                    assert error is None and result.state == "Cancelled"
                    assert get_own_open_attempt(session, actor_user_id=cashier_id, role="Cashier") is None
                    assert get_own_attempt_by_key(session, actor_user_id=cashier_id, role="Cashier",
                                                  idempotency_key=key).state == "Cancelled"
                    session.flush()
                    result, error = cancel_sale_attempt(session, attempt_id=direct.id,
                                                        actor_user_id=owner_id, role="Owner", request=cancel)
                    session.flush()
                    assert result is None and error.status_code == 409
                    with pytest.raises(ApiError) as error:
                        reserve_sale_attempt(session, _direct(), actor_user_id=cashier_id,
                                             role="Cashier", idempotency_key=key)
                    assert error.value.status_code == 409
                    session.expire_all()

                    occurred = connection.scalar(text("SELECT clock_timestamp()")) - timedelta(minutes=1)
                    paper = "PAPER-" + occurred.astimezone(ZoneInfo("Asia/Manila")).strftime("%Y%m%d") + "-001"
                    manual_key = uuid4()
                    manual, retry = reserve_sale_attempt(session, _manual(" " + paper.lower() + " ", occurred),
                                                         actor_user_id=owner_id, role="Owner", idempotency_key=manual_key)
                    session.flush()
                    assert retry is False and manual.manual_reference == paper
                    assert manual.direct_reference is None
                    assert get_own_attempt_by_key(session, actor_user_id=owner_id, role="Owner",
                                                  idempotency_key=manual_key).manual_reference == paper
                    replay, retry = reserve_sale_attempt(session, _manual(paper, occurred),
                                                         actor_user_id=owner_id, role="Owner", idempotency_key=manual_key)
                    assert retry is True and replay.id == manual.id
                    assert investigate_attempts(session, role="Owner", query=AttemptInvestigation(
                        recording_user_id=owner_id, reference=paper,
                    ))[0].id == manual.id
                    session.expire_all()
                    with pytest.raises(ApiError) as error:
                        reserve_sale_attempt(session, _manual(paper, occurred), actor_user_id=cashier_id,
                                             role="Cashier", idempotency_key=uuid4())
                    assert error.value.code == "duplicate_paper_reference"
                    session.expire_all()

                    # A failed audit flush must roll back the state change as well.
                    from unittest.mock import patch
                    failed_action = session.begin_nested()
                    try:
                        with patch("app.modules.transactions.attempt_service._audit_cancellation", side_effect=RuntimeError):
                            with pytest.raises(RuntimeError):
                                cancel_sale_attempt(session, attempt_id=manual.id,
                                                    actor_user_id=owner_id, role="Owner", request=cancel)
                    finally:
                        failed_action.rollback()
                        session.expire_all()
                    assert session.get(SaleAttempt, manual.id).state == "Reserved"
                    assert session.scalar(select(sa.func.count()).select_from(AuditEvent).where(
                        AuditEvent.resource_type == "sale_attempt", AuditEvent.resource_id == str(manual.id))) == 0
                    session.expire_all()
                    audits = session.scalars(select(AuditEvent).where(
                        AuditEvent.resource_type == "sale_attempt", AuditEvent.resource_id == str(direct.id),
                    )).all()
                    assert [event.outcome for event in audits] == ["Failure", "Success", "Failure"]
                    assert all("gcash_reference" not in (event.event_metadata or {}) for event in audits)
                    session.expire_all()
                    result, error = cancel_sale_attempt(session, attempt_id=manual.id,
                                                        actor_user_id=owner_id, role="Owner", request=cancel)
                    session.flush()
                    assert error is None and result.state == "Cancelled"
                    with pytest.raises(ApiError) as error:
                        reserve_sale_attempt(session, _manual(paper, occurred), actor_user_id=owner_id,
                                             role="Owner", idempotency_key=uuid4())
                    assert error.value.code == "duplicate_paper_reference"
                    session.expire_all()
                    second_direct, retry = reserve_sale_attempt(session, _direct(), actor_user_id=owner_id,
                                                                 role="Owner", idempotency_key=uuid4())
                    session.flush()
                    assert retry is False and second_direct.direct_reference != direct.direct_reference
                    synthetic_sale_id = connection.scalar(text(
                        "INSERT INTO transactions (business_date,recorded_by_user_id,entry_source,payment_method) "
                        "VALUES (CURRENT_DATE,:user_id,'Direct','Cash') RETURNING id"
                    ), {"user_id": owner_id})
                    connection.execute(text(
                        "UPDATE sale_attempts SET state='Committed', transaction_id=:sale_id, "
                        "committed_at=clock_timestamp() WHERE id=:id"
                    ), {"sale_id": synthetic_sale_id, "id": second_direct.id})
                    session.expire_all()
                    result, error = cancel_sale_attempt(session, attempt_id=second_direct.id,
                                                        actor_user_id=owner_id, role="Owner", request=cancel)
                    assert result is None and error.status_code == 409
                finally:
                    session.close()
            finally:
                scope.rollback()
                connection.rollback()
        with engine.connect() as verifier:
            _preflight(verifier, url)
            assert (
                verifier.scalar(text("SELECT count(*) FROM transactions")),
                verifier.scalar(text("SELECT count(*) FROM sale_idempotency")),
            ) == legacy_before
    finally:
        engine.dispose()
