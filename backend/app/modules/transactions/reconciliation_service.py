"""Owner investigation and positive-only acknowledgment of a known sale key."""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.transactions.idempotency_lock import try_lock_sale_key
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction
from app.modules.transactions.service import _database_time, _public_sale, lookup_sale_key
from app.modules.users.models import User


def investigate_sale(session: Session, *, recording_user_id: int, key: UUID):
    if session.get(User, recording_user_id) is None:
        raise ApiError(404, "not_found", "Recording user not found")
    status, sale = lookup_sale_key(session, actor_user_id=recording_user_id, idempotency_key=key)
    if sale is not None and sale.recorded_by_user_id != recording_user_id:
        raise ApiError(409, "sale_not_confirmed", "Committed sale is not available")
    return status, sale


def _audit(session: Session, *, actor_user_id: int, recording_user_id: int,
           key: UUID, outcome: str, transaction_id: int | None = None) -> None:
    digest = hashlib.sha256(f"{recording_user_id}:{key}".encode("ascii")).hexdigest()
    session.add(AuditEvent(
        actor_user_id=actor_user_id, event_type="SaleReconciliationAcknowledged",
        resource_type="transaction" if transaction_id is not None else "sale_idempotency",
        resource_id=str(transaction_id) if transaction_id is not None else digest,
        outcome=outcome, occurred_at=_database_time(session),
        event_metadata={"recording_user_id": recording_user_id, "key_digest": digest},
    ))
    session.flush()


def reject_acknowledgment(session: Session, *, actor_user_id: int,
                          recording_user_id: int, key: UUID) -> None:
    _audit(session, actor_user_id=actor_user_id, recording_user_id=recording_user_id,
           key=key, outcome="Failure")


def acknowledge_sale(session: Session, *, actor_user_id: int,
                     recording_user_id: int, key: UUID):
    """Return (sale, error). Caller commits the audit before raising an API error."""
    if session.get(User, recording_user_id) is None:
        reject_acknowledgment(session, actor_user_id=actor_user_id,
                              recording_user_id=recording_user_id, key=key)
        return None, ApiError(404, "not_found", "Recording user not found")
    if not try_lock_sale_key(session, recording_user_id, key):
        reject_acknowledgment(session, actor_user_id=actor_user_id,
                              recording_user_id=recording_user_id, key=key)
        return None, ApiError(409, "sale_processing", "Sale is still processing")
    claim = session.scalar(select(SaleIdempotency).where(
        SaleIdempotency.user_id == recording_user_id,
        SaleIdempotency.idempotency_key == str(key),
    ))
    transaction = session.get(Transaction, claim.transaction_id) if claim and claim.transaction_id else None
    if transaction is None or transaction.recorded_by_user_id != recording_user_id:
        reject_acknowledgment(session, actor_user_id=actor_user_id,
                              recording_user_id=recording_user_id, key=key)
        return None, ApiError(409, "sale_not_confirmed", "Committed sale is not available")
    try:
        sale = _public_sale(session, transaction.id)
    except ApiError:
        reject_acknowledgment(session, actor_user_id=actor_user_id,
                              recording_user_id=recording_user_id, key=key)
        return None, ApiError(409, "sale_not_confirmed", "Committed sale is not available")
    _audit(session, actor_user_id=actor_user_id, recording_user_id=recording_user_id,
           key=key, outcome="Success", transaction_id=transaction.id)
    return sale, None
