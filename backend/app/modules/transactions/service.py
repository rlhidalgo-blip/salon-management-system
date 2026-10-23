"""Atomic direct sales. Caller owns commit; rule locks precede catalog/staff locks.

Catalog writers and rule deactivation use the same rule-first protocol. Direct SQL
writers bypass that application-level guarantee. Concurrent same-key retries are
serialized by the PostgreSQL unique index; the losing insert rolls back only its
savepoint and reads the committed winning sale.
"""

import hashlib
import json
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.calculations import ZERO, calculate_item
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.idempotency_lock import lock_sale_key, try_lock_sale_key
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.schemas import SaleCreate, SaleItemPublic, SalePublic


def _database_time(session: Session) -> datetime:
    return session.scalar(select(func.clock_timestamp()))


def _fingerprint(payload: SaleCreate) -> str:
    # Validated/normalized JSON, including item order, is stable across retries.
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _public_sale(session: Session, transaction_id: int) -> SalePublic:
    sale = session.get(Transaction, transaction_id)
    if sale is None:
        raise ApiError(409, "incomplete_sale", "Sale is not available")
    items = list(session.scalars(select(TransactionItem).where(
        TransactionItem.transaction_id == transaction_id).order_by(TransactionItem.id)))
    if not items:
        raise ApiError(409, "incomplete_sale", "Sale is not available")
    return SalePublic(
        id=sale.id, date_time=sale.date_time, business_date=sale.business_date,
        recorded_by_user_id=sale.recorded_by_user_id, payment_method=sale.payment_method,
        gcash_reference=sale.gcash_reference, status=sale.status,
        items=[SaleItemPublic.model_validate(item) for item in items],
        gross_sales=sum((item.selling_price for item in items), ZERO),
        total_staff_commission=sum((item.staff_commission for item in items), ZERO),
        total_business_share=sum((item.business_share for item in items), ZERO),
    )


def record_direct_sale(session: Session, payload: SaleCreate, *, actor_user_id: int,
                       idempotency_key: UUID) -> tuple[SalePublic, bool]:
    """Run inside one caller-owned transaction. bool is True for an identical retry."""
    # This must precede the claim, catalog/rule locks and any sale writes.
    lock_sale_key(session, actor_user_id, idempotency_key)
    key = str(idempotency_key)
    fingerprint = _fingerprint(payload)
    now = _database_time(session)
    try:
        with session.begin_nested():
            claim = SaleIdempotency(user_id=actor_user_id, idempotency_key=key,
                                    request_hash=fingerprint, created_at=now)
            session.add(claim)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(SaleIdempotency).where(
            SaleIdempotency.user_id == actor_user_id,
            SaleIdempotency.idempotency_key == key,
        ).with_for_update())
        if existing is None:
            raise ApiError(409, "idempotency_conflict", "Idempotency key could not be resolved")
        if existing.request_hash != fingerprint:
            raise ApiError(409, "idempotency_conflict", "Idempotency key was used for another request")
        if existing.transaction_id is None:
            raise ApiError(409, "incomplete_sale", "Sale is not available")
        return _public_sale(session, existing.transaction_id), True

    # Read only rule IDs, then lock all rules in ascending order. Recheck the
    # catalog rows after locking them; stale rule assignments fail closed.
    catalog_keys = sorted({("service", item.service_id) if item.service_id is not None
                           else ("product", item.product_id) for item in payload.items})
    rule_ids = {}
    for kind, item_id in catalog_keys:
        model = Service if kind == "service" else Product
        rule_id = session.scalar(select(model.commission_rule_id).where(model.id == item_id))
        if rule_id is None:
            raise ApiError(404, "not_found", "Catalog item not found")
        rule_ids[(kind, item_id)] = rule_id
    rules = {}
    for rule_id in sorted(set(rule_ids.values())):
        rule = session.scalar(select(CommissionRule).where(CommissionRule.id == rule_id).with_for_update())
        if rule is None or not rule.active:
            raise ApiError(409, "rule_inactive", "Commission rule is not active")
        rules[rule_id] = rule
    catalog = {}
    for kind, item_id in catalog_keys:
        model = Service if kind == "service" else Product
        item = session.scalar(select(model).where(model.id == item_id).with_for_update()
                              .execution_options(populate_existing=True))
        if item is None or not item.active or item.commission_rule_id != rule_ids[(kind, item_id)]:
            raise ApiError(409, "catalog_changed", "Catalog item is unavailable or changed; retry")
        rule = rules[item.commission_rule_id]
        if rule.type != ("Percentage" if kind == "service" else "Fixed"):
            raise ApiError(409, "invalid_rule_type", "Catalog commission rule is incompatible")
        catalog[(kind, item_id)] = item
    staff = {}
    for staff_id in sorted({item.staff_id for item in payload.items if item.staff_id is not None}):
        member = session.scalar(select(Staff).where(Staff.id == staff_id).with_for_update())
        if member is None or not member.active:
            raise ApiError(409, "staff_inactive", "Assigned staff member is unavailable")
        staff[staff_id] = member

    # Re-read trusted time after any lock waits, so a request crossing Manila
    # midnight is recorded on the actual sale-creation business date.
    sale_time = _database_time(session)
    sale = Transaction(date_time=sale_time, business_date=sale_time.astimezone(ZoneInfo("Asia/Manila")).date(),
                       recorded_by_user_id=actor_user_id, entry_source="Direct",
                       payment_method=payload.payment_method, gcash_reference=payload.gcash_reference,
                       status="Completed")
    session.add(sale)
    session.flush()
    for requested in payload.items:
        kind = "service" if requested.service_id is not None else "product"
        catalog_id = requested.service_id if kind == "service" else requested.product_id
        item = catalog[(kind, catalog_id)]
        rule = rules[item.commission_rule_id]
        if (kind == "product" or not item.allows_variable_price) and requested.selling_price != item.current_price:
            raise ApiError(422, "price_mismatch", "Selling price must match current catalog price")
        if kind == "product" and requested.staff_id is None:
            commission_type, commission_value = None, None
        else:
            commission_type, commission_value = rule.type, rule.value
        commission, share = calculate_item(requested.selling_price, commission_type, commission_value)
        session.add(TransactionItem(
            transaction_id=sale.id, service_id=requested.service_id, product_id=requested.product_id,
            staff_id=requested.staff_id, item_name_snapshot=item.name,
            selling_price=requested.selling_price, commission_type_snapshot=commission_type,
            commission_value_snapshot=commission_value, staff_commission=commission, business_share=share,
        ))
    session.flush()
    claim.transaction_id = sale.id
    session.flush()
    return _public_sale(session, sale.id), False


def lookup_sale_key(session: Session, *, actor_user_id: int, idempotency_key: UUID):
    """A missing claim is only a point-in-time observation, never finality."""
    if not try_lock_sale_key(session, actor_user_id, idempotency_key):
        return "processing", None
    claim = session.scalar(select(SaleIdempotency).where(
        SaleIdempotency.user_id == actor_user_id,
        SaleIdempotency.idempotency_key == str(idempotency_key),
    ))
    if claim is None:
        return "not_committed_at_check", None
    if claim.transaction_id is None:
        raise ApiError(409, "incomplete_sale", "Sale is not available")
    return "committed", _public_sale(session, claim.transaction_id)
