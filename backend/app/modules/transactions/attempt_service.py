"""Sale-attempt operations used by feature-gated routes and writers.

Callers own commit/rollback. The reservation protocol is disabled by default.

Lock order: user/key advisory lock, Manual-reference advisory lock when needed,
attempt row, then rule/catalog/staff locks. PostgreSQL unique indexes remain
the final same-table race safeguards.
"""

import hashlib
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.transactions.attempt_models import SaleAttempt
from app.modules.transactions.attempt_schemas import (
    AttemptInvestigation, AttemptPublic, CancellationRequest, DirectReservation,
    ManualReservation,
)
from app.modules.transactions.idempotency_lock import (
    bound_sale_waits, lock_manual_reference, lock_sale_key, retryable_sale_waits,
)
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction
from app.modules.transactions.manual_service import _fingerprint as manual_fingerprint
from app.modules.transactions.service import _database_time, _fingerprint as direct_fingerprint


def _public(attempt: SaleAttempt) -> AttemptPublic:
    return AttemptPublic.model_validate(attempt)


@retryable_sale_waits
def reserve_sale_attempt(session: Session, request: DirectReservation | ManualReservation, *,
                         actor_user_id: int, role: str, idempotency_key: UUID) -> tuple[AttemptPublic, bool]:
    """Reserve a frozen validated payload. True means identical same-key retry.

    A successful caller must commit before reporting confirmation to a browser.
    No full payload or payment reference is persisted in the attempt row.
    """
    if role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")
    if not isinstance(idempotency_key, UUID) or not isinstance(request, (DirectReservation, ManualReservation)):
        raise ApiError(422, "validation_error", "Invalid reservation request")
    bound_sale_waits(session)
    lock_sale_key(session, actor_user_id, idempotency_key)
    fingerprint = (direct_fingerprint(request.sale) if isinstance(request, DirectReservation)
                   else manual_fingerprint(request.sale))
    existing = session.scalar(select(SaleAttempt).where(
        SaleAttempt.user_id == actor_user_id, SaleAttempt.idempotency_key == idempotency_key,
    ).with_for_update())
    if existing is not None:
        if existing.state == "Cancelled" or existing.source != request.source or existing.request_hash != fingerprint:
            raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable")
        return _public(existing), True
    if session.scalar(select(SaleIdempotency.id).where(
        SaleIdempotency.user_id == actor_user_id,
        SaleIdempotency.idempotency_key == str(idempotency_key),
    )) is not None:
        # Old committed sales remain replayable through their existing POST route, not a new reservation.
        raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable")
    if session.scalar(select(SaleAttempt.id).where(
        SaleAttempt.user_id == actor_user_id, SaleAttempt.state == "Reserved",
    )) is not None:
        raise ApiError(409, "open_sale_attempt", "An unresolved sale attempt already exists")

    manual_reference = None
    if isinstance(request, ManualReservation):
        now = _database_time(session)
        occurrence = request.sale.date_time
        business_date = occurrence.astimezone(ZoneInfo("Asia/Manila")).date()
        if request.sale.manual_reference[6:14] != business_date.strftime("%Y%m%d"):
            raise ApiError(422, "paper_date_mismatch", "Paper reference date does not match sale business date")
        if occurrence > now:
            raise ApiError(422, "future_sale", "Manual sale occurrence time cannot be in the future")
        if role == "Cashier" and business_date != now.astimezone(ZoneInfo("Asia/Manila")).date():
            raise ApiError(403, "forbidden", "Previous-day manual entry requires Owner access")
        manual_reference = request.sale.manual_reference
        lock_manual_reference(session, manual_reference)
        if session.scalar(select(Transaction.id).where(Transaction.manual_reference == manual_reference)) is not None:
            raise ApiError(409, "duplicate_paper_reference", "Paper reference is already reserved")

    try:
        with session.begin_nested():
            attempt = SaleAttempt(
                user_id=actor_user_id, idempotency_key=idempotency_key, source=request.source,
                state="Reserved", request_hash=fingerprint, manual_reference=manual_reference,
            )
            session.add(attempt)
            session.flush()
            session.refresh(attempt)
    except IntegrityError as exc:
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if name == "uq_sale_attempts_user_key":
            winner = session.scalar(select(SaleAttempt).where(
                SaleAttempt.user_id == actor_user_id, SaleAttempt.idempotency_key == idempotency_key,
            ).with_for_update())
            if (winner is not None and winner.state != "Cancelled" and winner.source == request.source
                    and winner.request_hash == fingerprint):
                return _public(winner), True
        if name in ("uq_sale_attempts_manual_reference", "uq_transactions_manual_reference"):
            raise ApiError(409, "duplicate_paper_reference", "Paper reference is already reserved") from None
        if name == "uq_sale_attempts_one_reserved_user":
            raise ApiError(409, "open_sale_attempt", "An unresolved sale attempt already exists") from None
        raise
    return _public(attempt), False


def get_own_open_attempt(session: Session, *, actor_user_id: int, role: str) -> AttemptPublic | None:
    if role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")
    attempt = session.scalar(select(SaleAttempt).where(
        SaleAttempt.user_id == actor_user_id, SaleAttempt.state == "Reserved",
    ))
    return _public(attempt) if attempt else None


def get_own_attempt_by_key(session: Session, *, actor_user_id: int, role: str,
                           idempotency_key: UUID) -> AttemptPublic:
    """Return only the authenticated user's exact attempt, including durable fences."""
    if role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")
    attempt = session.scalar(select(SaleAttempt).where(
        SaleAttempt.user_id == actor_user_id,
        SaleAttempt.idempotency_key == idempotency_key,
    ))
    if attempt is None:
        raise ApiError(404, "not_found", "Sale attempt not found")
    return _public(attempt)


def get_attempt_detail(session: Session, *, attempt_id: int, actor_user_id: int,
                       role: str) -> AttemptPublic:
    if role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")
    attempt = session.get(SaleAttempt, attempt_id)
    if attempt is None or (role != "Owner" and attempt.user_id != actor_user_id):
        raise ApiError(404, "not_found", "Sale attempt not found")
    return _public(attempt)


def investigate_attempts(session: Session, *, role: str,
                         query: AttemptInvestigation) -> list[AttemptPublic]:
    if role != "Owner":
        raise ApiError(403, "forbidden", "Insufficient permissions")
    statement = select(SaleAttempt).where(SaleAttempt.user_id == query.recording_user_id)
    if query.created_from is not None:
        statement = statement.where(SaleAttempt.created_at >= query.created_from)
    if query.created_before is not None:
        statement = statement.where(SaleAttempt.created_at < query.created_before)
    if query.reference is not None:
        statement = statement.where(or_(SaleAttempt.direct_reference == query.reference,
                                        SaleAttempt.manual_reference == query.reference))
    if query.before_id is not None:
        statement = statement.where(SaleAttempt.id < query.before_id)
    attempts = session.scalars(statement.order_by(SaleAttempt.id.desc()).limit(query.limit)).all()
    return [_public(attempt) for attempt in attempts]


def _audit_cancellation(session: Session, *, actor_user_id: int, attempt_id: int,
                        outcome: str, target: SaleAttempt | None = None) -> None:
    metadata = None
    if target is not None:
        metadata = {
            "recording_user_id": target.user_id,
            "key_digest": hashlib.sha256(f"{target.user_id}:{target.idempotency_key}".encode("ascii")).hexdigest(),
        }
    session.add(AuditEvent(
        actor_user_id=actor_user_id, event_type="SaleAttemptCancellation",
        resource_type="sale_attempt", resource_id=str(attempt_id), outcome=outcome,
        occurred_at=_database_time(session), event_metadata=metadata,
    ))
    session.flush()


@retryable_sale_waits
def cancel_sale_attempt(session: Session, *, attempt_id: int, actor_user_id: int,
                        role: str, request: CancellationRequest) -> tuple[AttemptPublic | None, ApiError | None]:
    """Return result/error so caller can commit a safely rejected audit before raising.

    Authorization is enforced here too; future route must additionally apply Origin/CSRF.
    UI confirmation is a separate future frontend requirement.
    """
    if role != "Owner":
        _audit_cancellation(session, actor_user_id=actor_user_id, attempt_id=attempt_id, outcome="Failure")
        return None, ApiError(403, "forbidden", "Insufficient permissions")
    if attempt_id <= 0 or not isinstance(request, CancellationRequest):
        raise ApiError(422, "validation_error", "Invalid cancellation request")
    bound_sale_waits(session)
    initial = session.get(SaleAttempt, attempt_id)
    if initial is None:
        _audit_cancellation(session, actor_user_id=actor_user_id, attempt_id=attempt_id, outcome="Failure")
        return None, ApiError(404, "not_found", "Sale attempt not found")
    lock_sale_key(session, initial.user_id, initial.idempotency_key)
    attempt = session.scalar(select(SaleAttempt).where(SaleAttempt.id == attempt_id)
                             .with_for_update().execution_options(populate_existing=True))
    if attempt is None or attempt.user_id != initial.user_id or attempt.idempotency_key != initial.idempotency_key:
        _audit_cancellation(session, actor_user_id=actor_user_id, attempt_id=attempt_id, outcome="Failure")
        return None, ApiError(409, "attempt_changed", "Sale attempt changed")
    if attempt.state != "Reserved":
        _audit_cancellation(session, actor_user_id=actor_user_id, attempt_id=attempt_id,
                            outcome="Failure", target=attempt)
        return None, ApiError(409, "attempt_not_reserved", "Sale attempt cannot be cancelled")
    attempt.state = "Cancelled"
    attempt.cancelled_at = _database_time(session)
    attempt.cancelled_by_user_id = actor_user_id
    attempt.cancellation_reason = request.reason
    session.flush()
    _audit_cancellation(session, actor_user_id=actor_user_id, attempt_id=attempt_id,
                        outcome="Success", target=attempt)
    return _public(attempt), None
