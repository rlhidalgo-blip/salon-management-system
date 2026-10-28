"""Verified paper sales; historical values are supplied from retained evidence, never current catalog."""

import hashlib
import json
from datetime import timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Product, Service
from app.modules.staff.models import Staff
from app.modules.transactions.calculations import calculate_item
from app.modules.transactions.attempt_write_guard import (
    committed_claim_or_none, mark_attempt_committed, require_reserved_attempt,
)
from app.modules.transactions.idempotency_lock import (
    bound_sale_waits, lock_manual_reference, lock_sale_key, retryable_sale_waits,
)
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.schemas import ManualSaleCreate, SalePublic
from app.modules.transactions.service import _database_time, _public_sale


MANILA = ZoneInfo("Asia/Manila")


def _fingerprint(payload: ManualSaleCreate) -> str:
    # Pydantic has already normalized the paper reference before this hash.
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(("Manual:" + canonical).encode("utf-8")).hexdigest()


def _reference_conflict(exc: IntegrityError) -> bool:
    diagnostic = getattr(exc.orig, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == "uq_transactions_manual_reference":
        return True
    # Fast SQLite tests have no PostgreSQL diagnostic object.
    return "UNIQUE constraint failed: transactions.manual_reference" in str(exc.orig)


def _existing_claim(session: Session, actor_user_id: int, key: str,
                    fingerprint: str) -> SalePublic | None:
    claim = session.scalar(select(SaleIdempotency).where(
        SaleIdempotency.user_id == actor_user_id,
        SaleIdempotency.idempotency_key == key,
    ).with_for_update())
    if claim is None:
        return None
    if claim.request_hash != fingerprint:
        raise ApiError(409, "idempotency_conflict", "Idempotency key was used for another request")
    if claim.transaction_id is None:
        raise ApiError(409, "incomplete_sale", "Sale is not available")
    return _public_sale(session, claim.transaction_id)


@retryable_sale_waits
def record_manual_sale(session: Session, payload: ManualSaleCreate, *, actor_user_id: int,
                       role: str, idempotency_key: UUID,
                       enforce_reservation: bool = False) -> tuple[SalePublic, bool]:
    """Run inside one caller-owned transaction; True means an identical committed replay.

    Attestation is an operational acknowledgment, not proof that external paper
    or historical configuration was independently verified by this database.
    """
    # The public route remains on the legacy path until the coordinated cutover.
    if enforce_reservation:
        bound_sale_waits(session)
    lock_sale_key(session, actor_user_id, idempotency_key)
    key = str(idempotency_key)
    fingerprint = _fingerprint(payload)
    attempt = None
    if enforce_reservation:
        claim = committed_claim_or_none(session, user_id=actor_user_id, key=idempotency_key,
                                        source="Manual", fingerprint=fingerprint,
                                        manual_reference=payload.manual_reference)
        replay = _public_sale(session, claim.transaction_id) if claim is not None else None
    else:
        replay = _existing_claim(session, actor_user_id, key, fingerprint)
    if replay is not None:
        return replay, True

    if enforce_reservation:
        lock_manual_reference(session, payload.manual_reference)
        attempt = require_reserved_attempt(session, user_id=actor_user_id, key=idempotency_key,
                                           source="Manual", fingerprint=fingerprint,
                                           manual_reference=payload.manual_reference)
        # A Voided or legacy committed sale still owns its paper reference.
        if session.scalar(select(Transaction.id).where(
                Transaction.manual_reference == payload.manual_reference)) is not None:
            raise ApiError(409, "duplicate_paper_reference", "Paper reference is already recorded")

    occurrence = payload.date_time.astimezone(timezone.utc)
    business_date = occurrence.astimezone(MANILA).date()
    if payload.manual_reference[6:14] != business_date.strftime("%Y%m%d"):
        raise ApiError(422, "paper_date_mismatch", "Paper reference date does not match sale business date")

    # Read IDs, then lock catalog rows and staff rows in deterministic order.
    # Historical snapshots do not use today's rule/price/active flags.
    catalog_keys = sorted({("service", item.service_id) if item.service_id is not None
                           else ("product", item.product_id) for item in payload.items})
    for kind, item_id in catalog_keys:
        model = Service if kind == "service" else Product
        if session.scalar(select(model.id).where(model.id == item_id).with_for_update()) is None:
            raise ApiError(404, "not_found", "Historical catalog item not found")
    for staff_id in sorted({item.staff_id for item in payload.items if item.staff_id is not None}):
        if session.scalar(select(Staff.id).where(Staff.id == staff_id).with_for_update()) is None:
            raise ApiError(404, "not_found", "Historical staff member not found")

    # Recheck after all lock waits; a Cashier request crossing midnight cannot
    # quietly become a previous-day back-entry.
    now = _database_time(session)
    if occurrence > now:
        raise ApiError(422, "future_sale", "Manual sale occurrence time cannot be in the future")
    if role == "Cashier" and business_date != now.astimezone(MANILA).date():
        raise ApiError(403, "forbidden", "Previous-day manual entry requires Owner access")
    if role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")

    # An existing Voided transaction still owns its paper reference.
    if not enforce_reservation and session.scalar(select(Transaction.id).where(
            Transaction.manual_reference == payload.manual_reference)) is not None:
        raise ApiError(409, "duplicate_paper_reference", "Paper reference is already recorded")

    # The unique indexes are final race safeguards. Savepoints allow a precise
    # 409 without masking unrelated integrity errors or leaving a failed session.
    try:
        with session.begin_nested():
            claim = SaleIdempotency(user_id=actor_user_id, idempotency_key=key,
                                    request_hash=fingerprint, created_at=now)
            session.add(claim)
            session.flush()
    except IntegrityError:
        if enforce_reservation:
            claim = committed_claim_or_none(session, user_id=actor_user_id, key=idempotency_key,
                                            source="Manual", fingerprint=fingerprint,
                                            manual_reference=payload.manual_reference)
            if claim is None:
                raise ApiError(409, "idempotency_conflict", "Sale attempt key is unavailable") from None
            return _public_sale(session, claim.transaction_id), True
        replay = _existing_claim(session, actor_user_id, key, fingerprint)
        if replay is not None:
            return replay, True
        raise ApiError(409, "idempotency_conflict", "Idempotency key could not be resolved") from None

    try:
        with session.begin_nested():
            sale = Transaction(date_time=occurrence, business_date=business_date,
                               created_at=now, recorded_by_user_id=actor_user_id,
                               entry_source="Manual", manual_reference=payload.manual_reference,
                               payment_method=payload.payment_method,
                               gcash_reference=payload.gcash_reference, status="Completed")
            session.add(sale)
            session.flush()
            for requested in payload.items:
                commission, share = calculate_item(
                    requested.selling_price, requested.commission_type_snapshot,
                    requested.commission_value_snapshot)
                session.add(TransactionItem(
                    transaction_id=sale.id, service_id=requested.service_id,
                    product_id=requested.product_id, staff_id=requested.staff_id,
                    item_name_snapshot=requested.item_name_snapshot,
                    selling_price=requested.selling_price,
                    commission_type_snapshot=requested.commission_type_snapshot,
                    commission_value_snapshot=requested.commission_value_snapshot,
                    staff_commission=commission, business_share=share,
                ))
            session.flush()
            claim.transaction_id = sale.id
            audit = AuditEvent(
                actor_user_id=actor_user_id, event_type="ManualSaleCreated",
                resource_type="transaction", resource_id=str(sale.id), outcome="Success",
                occurred_at=now,
                event_metadata={"manual_reference": payload.manual_reference,
                                "business_date": business_date.isoformat()},
            )
            session.add(audit)
            session.flush()
            # A unique-index wait can outlive Manila midnight even after the
            # catalog/staff locks were checked. Roll back the entire attempt.
            completed_at = _database_time(session)
            if role == "Cashier" and business_date != completed_at.astimezone(MANILA).date():
                raise ApiError(403, "forbidden", "Previous-day manual entry requires Owner access")
            sale.created_at = completed_at
            audit.occurred_at = completed_at
            session.flush()
            if attempt is not None:
                mark_attempt_committed(session, attempt, sale.id)
    except IntegrityError as exc:
        if _reference_conflict(exc):
            raise ApiError(409, "duplicate_paper_reference", "Paper reference is already recorded") from None
        raise
    return _public_sale(session, sale.id), False
