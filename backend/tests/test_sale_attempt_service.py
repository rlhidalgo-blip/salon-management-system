"""B1 internal-service contracts. No attempt endpoint is registered in this checkpoint."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.exceptions import ApiError
from app.main import app
from app.modules.transactions.attempt_schemas import (
    AttemptInvestigation, CancellationRequest, DirectReservation, ManualReservation,
    ReservationRequest,
)
from app.modules.transactions.attempt_service import (
    cancel_sale_attempt, get_own_attempt_by_key, get_own_open_attempt,
    investigate_attempts, reserve_sale_attempt,
)


def _direct():
    return {"source": "Direct", "sale": {"payment_method": "Cash", "items": [
        {"service_id": 1, "staff_id": 1, "selling_price": "100.00"},
    ]}}


def test_strict_reservation_validation_and_normalization():
    adapter = TypeAdapter(ReservationRequest)
    assert isinstance(adapter.validate_python(_direct()), DirectReservation)
    for changed in (
        {**_direct(), "unknown": True},
        {**_direct(), "source": "Other"},
        {**_direct(), "sale": {**_direct()["sale"], "unknown": True}},
        {**_direct(), "source": "Manual"},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(changed)
    manual = adapter.validate_python({"source": "Manual", "sale": {
        "date_time": "2026-10-27T12:00:00+08:00", "manual_reference": " paper-20261027-001 ",
        "verified_against_paper": True, "payment_method": "Cash", "items": [
            {"service_id": 1, "staff_id": 1, "selling_price": "100.00",
             "item_name_snapshot": "Haircut", "commission_type_snapshot": "Percentage",
             "commission_value_snapshot": "50.00"},
        ],
    }})
    assert isinstance(manual, ManualReservation)
    assert manual.sale.manual_reference == "PAPER-20261027-001"


def test_cancellation_and_investigation_validation():
    for payload in ({"reason": " ", "evidence_verified": True},
                    {"reason": "x" * 501, "evidence_verified": True},
                    {"reason": "Valid", "evidence_verified": False},
                    {"reason": "Valid", "evidence_verified": True, "extra": 1}):
        with pytest.raises(ValidationError):
            CancellationRequest.model_validate(payload)
    assert CancellationRequest(reason="  checked  ", evidence_verified=True).reason == "checked"
    for payload in ({"recording_user_id": 1, "limit": 101},
                    {"recording_user_id": 1, "created_from": datetime(2026, 1, 1)},
                    {"recording_user_id": 1, "reference": "other"},
                    {"recording_user_id": 1, "unknown": 1}):
        with pytest.raises(ValidationError):
            AttemptInvestigation.model_validate(payload)


def test_b1_services_are_not_public_routes():
    assert not any("/attempts" in getattr(route, "path", "") for route in app.routes)


def test_role_checks_fail_before_database_access():
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError("database was accessed")

    db = NoDatabase()
    with pytest.raises(ApiError) as error:
        reserve_sale_attempt(db, TypeAdapter(ReservationRequest).validate_python(_direct()),
                             actor_user_id=1, role="Visitor", idempotency_key=uuid4())
    assert error.value.status_code == 403
    with pytest.raises(ApiError) as error:
        get_own_open_attempt(db, actor_user_id=1, role="Visitor")
    assert error.value.status_code == 403
    with pytest.raises(ApiError) as error:
        get_own_attempt_by_key(db, actor_user_id=1, role="Visitor", idempotency_key=uuid4())
    assert error.value.status_code == 403
    with pytest.raises(ApiError) as error:
        investigate_attempts(db, role="Cashier", query=AttemptInvestigation(recording_user_id=1))
    assert error.value.status_code == 403
