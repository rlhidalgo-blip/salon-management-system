"""Catalog writes lock the CommissionRule before the item, in one caller-owned transaction.

Every application catalog writer must use this order. Direct SQL writers bypass it.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.commissions.service import lock_rule_for_catalog_assignment


def _rule(session: Session, rule_id: int, *, require_active: bool) -> CommissionRule:
    if require_active:
        return lock_rule_for_catalog_assignment(session, rule_id)
    rule = session.scalar(select(CommissionRule).where(CommissionRule.id == rule_id).with_for_update())
    if rule is None:
        raise ApiError(404, "not_found", "Commission rule not found")
    return rule


def _validate_rule(rule: CommissionRule, *, kind: str, price: Decimal, active: bool) -> None:
    expected = "Percentage" if kind == "service" else "Fixed"
    if rule.type != expected:
        raise ApiError(422, "invalid_rule_type", f"{kind.title()} requires a {expected} commission rule")
    if kind == "product" and active and rule.value > price:
        raise ApiError(422, "commission_exceeds_price", "Fixed commission exceeds current product price")


def list_items(session: Session, kind: str) -> list[Service] | list[Product]:
    model = Service if kind == "service" else Product
    return list(session.scalars(select(model).order_by(model.id)))


def create_item(session: Session, kind: str, **values) -> Service | Product:
    model = Service if kind == "service" else Product
    rule = _rule(session, values["commission_rule_id"], require_active=True)
    _validate_rule(rule, kind=kind, price=values["current_price"], active=True)
    item = model(**values)
    session.add(item)
    session.flush()
    return item


def change_item(session: Session, kind: str, item_id: int, *, changes: dict) -> Service | Product:
    model = Service if kind == "service" else Product
    # Read the current rule ID without taking an item lock. All application
    # writers take rule locks first; a stale read is rejected after item lock.
    snapshot = session.execute(
        select(model.commission_rule_id, model.active).where(model.id == item_id)
    ).one_or_none()
    if snapshot is None:
        raise ApiError(404, "not_found", f"{kind.title()} not found")
    old_rule_id, old_active = snapshot
    target_rule_id = changes.get("commission_rule_id", old_rule_id)
    reassigning = "commission_rule_id" in changes and target_rule_id != old_rule_id
    activating = changes.get("active") is True
    # Only the target rule is needed: changing away from the old rule cannot
    # create an active reference to it. If a future write needs both rule rows,
    # it must lock them in ascending ID order before locking the item.
    rule = _rule(session, target_rule_id, require_active=bool(old_active or activating or reassigning))
    item = session.scalar(select(model).where(model.id == item_id).with_for_update())
    if item is None:
        raise ApiError(404, "not_found", f"{kind.title()} not found")
    if item.commission_rule_id != old_rule_id or item.active != old_active:
        raise ApiError(409, "catalog_changed", "Catalog item changed; retry with current values")
    new_active = changes.get("active", item.active)
    _validate_rule(rule, kind=kind, price=changes.get("current_price", item.current_price), active=new_active)
    for field, value in changes.items():
        setattr(item, field, value)
    session.flush()
    return item
