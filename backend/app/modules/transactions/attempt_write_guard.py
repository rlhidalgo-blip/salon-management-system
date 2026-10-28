"""Shared internal writer checks; not enabled by public routes until coordinated cutover."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.transactions.attempt_models import SaleAttempt
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction


def committed_claim_or_none(session: Session, *, user_id: int, key: UUID,
                            source: str, fingerprint: str,
                            manual_reference: str | None = None) -> SaleIdempotency | None:
    """Call after the user/key advisory lock; permit only exact legacy/new replay."""
    attempt = session.scalar(select(SaleAttempt).where(
        SaleAttempt.user_id == user_id, SaleAttempt.idempotency_key == key,
    ))
    if attempt is not None and attempt.state == "Cancelled":
        raise ApiError(409, "attempt_cancelled", "Sale attempt cannot be reused")
    claim = session.scalar(select(SaleIdempotency).where(
        SaleIdempotency.user_id == user_id,
        SaleIdempotency.idempotency_key == str(key),
    ).with_for_update())
    if claim is None:
        if attempt is not None and attempt.state == "Committed":
            raise ApiError(409, "incomplete_sale", "Sale attempt is inconsistent")
        return None
    if claim.request_hash != fingerprint or claim.transaction_id is None:
        raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable")
    transaction = session.get(Transaction, claim.transaction_id)
    if (transaction is None or transaction.recorded_by_user_id != user_id
            or transaction.entry_source != source
            or transaction.manual_reference != manual_reference):
        raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable")
    if attempt is not None and (attempt.state != "Committed" or attempt.source != source
                                or attempt.request_hash != fingerprint
                                or attempt.transaction_id != claim.transaction_id
                                or attempt.manual_reference != manual_reference
                                or (source == "Direct" and not attempt.direct_reference)):
        raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable")
    return claim


def require_reserved_attempt(session: Session, *, user_id: int, key: UUID,
                             source: str, fingerprint: str,
                             manual_reference: str | None = None) -> SaleAttempt:
    """Call after the user/key lock and, for Manual, the reference lock."""
    attempt = session.scalar(select(SaleAttempt).where(
        SaleAttempt.user_id == user_id, SaleAttempt.idempotency_key == key,
    ).with_for_update().execution_options(populate_existing=True))
    if attempt is None:
        raise ApiError(409, "reservation_required", "A confirmed sale reservation is required")
    if attempt.state == "Cancelled":
        raise ApiError(409, "attempt_cancelled", "Sale attempt cannot be reused")
    if (attempt.state != "Reserved" or attempt.source != source or attempt.request_hash != fingerprint
            or attempt.manual_reference != manual_reference
            or (source == "Direct" and not attempt.direct_reference)):
        raise ApiError(409, "idempotency_conflict", "Sale attempt does not match the request")
    return attempt


def mark_attempt_committed(session: Session, attempt: SaleAttempt, transaction_id: int) -> None:
    attempt.state = "Committed"
    attempt.transaction_id = transaction_id
    attempt.committed_at = session.scalar(select(func.clock_timestamp()))
    session.flush()
