"""Default-disabled sale-attempt API; share one cutover gate with both writers."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner_or_cashier
from app.modules.transactions.attempt_feature import require_attempt_protocol
from app.modules.transactions.attempt_schemas import (
    AttemptInvestigation, AttemptPublic, CancellationRequest, ReservationRequest,
)
from app.modules.transactions.attempt_service import (
    cancel_sale_attempt, get_attempt_detail, get_own_open_attempt,
    get_own_attempt_by_key, investigate_attempts, reserve_sale_attempt,
)


router = APIRouter(prefix="/api/v1/sales/attempts", tags=["sale attempts"],
                   dependencies=[Depends(require_attempt_protocol)])


@router.post("", response_model=AttemptPublic, status_code=201)
def post_attempt(payload: ReservationRequest, response: Response,
                 idempotency_key: UUID = Header(alias="Idempotency-Key"),
                 principal: Principal = Depends(require_owner_or_cashier),
                 session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        attempt, replayed = reserve_sale_attempt(
            session, payload, actor_user_id=principal.user_id,
            role=principal.role, idempotency_key=idempotency_key,
        )
    if replayed:
        response.status_code = 200
    return attempt


@router.get("/open", response_model=AttemptPublic | None)
def get_open_attempt(response: Response,
                     principal: Principal = Depends(require_owner_or_cashier),
                     session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return get_own_open_attempt(session, actor_user_id=principal.user_id, role=principal.role)


@router.get("/by-idempotency-key/{idempotency_key}", response_model=AttemptPublic)
def get_own_attempt_by_idempotency_key(response: Response, idempotency_key: UUID = Path(),
                                        principal: Principal = Depends(require_owner_or_cashier),
                                        session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return get_own_attempt_by_key(session, actor_user_id=principal.user_id,
                                      role=principal.role, idempotency_key=idempotency_key)


@router.get("", response_model=list[AttemptPublic])
def get_attempts(response: Response, recording_user_id: int = Query(gt=0),
                 created_from: datetime | None = None, created_before: datetime | None = None,
                 reference: str | None = None, limit: int = Query(default=50, ge=1, le=100),
                 before_id: int | None = Query(default=None, gt=0),
                 principal: Principal = Depends(require_owner_or_cashier),
                 session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    # Keep Cashier denial inside the authenticated service, before any lookup.
    try:
        query = AttemptInvestigation(
            recording_user_id=recording_user_id, created_from=created_from,
            created_before=created_before, reference=reference,
            limit=limit, before_id=before_id,
        )
    except ValidationError:
        raise ApiError(422, "validation_error", "Invalid request") from None
    with session.begin():
        return investigate_attempts(session, role=principal.role, query=query)


@router.get("/{attempt_id}", response_model=AttemptPublic)
def get_attempt(response: Response, attempt_id: int = Path(gt=0),
                principal: Principal = Depends(require_owner_or_cashier),
                session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return get_attempt_detail(session, attempt_id=attempt_id,
                                  actor_user_id=principal.user_id, role=principal.role)


@router.post("/{attempt_id}/cancel", response_model=AttemptPublic)
def post_cancel_attempt(payload: CancellationRequest, response: Response,
                        attempt_id: int = Path(gt=0),
                        principal: Principal = Depends(require_owner_or_cashier),
                        session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        attempt, error = cancel_sale_attempt(
            session, attempt_id=attempt_id, actor_user_id=principal.user_id,
            role=principal.role, request=payload,
        )
    if error is not None:
        raise error
    return attempt
