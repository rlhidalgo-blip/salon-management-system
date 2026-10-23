"""Commission configuration. Caller owns the transaction and commit.

Locking contract for *all future catalog write services*: before creating,
reassigning, or reactivating an active Service/Product, lock its target
CommissionRule row with lock_rule_for_catalog_assignment in the SAME database
transaction, check that it is active, then write. Acquire multiple rule locks
in ascending id order. Deactivation uses the same rule-row lock before checking
active references and writing. No protection is claimed for direct SQL writers.
"""

from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule


def list_rules(session: Session) -> list[CommissionRule]:
    return list(session.scalars(select(CommissionRule).order_by(CommissionRule.id)))


def create_rule(session: Session, *, name: str, type: str, value: Decimal, actor_user_id: int) -> CommissionRule:
    rule = CommissionRule(name=name, type=type, value=value)
    session.add(rule)
    session.flush()
    session.add(AuditEvent(
        actor_user_id=actor_user_id, event_type="CommissionRuleCreated",
        resource_type="commission_rule", resource_id=str(rule.id), outcome="Success",
    ))
    return rule


def _lock_rule(session: Session, rule_id: int) -> CommissionRule:
    rule = session.scalar(select(CommissionRule).where(CommissionRule.id == rule_id).with_for_update())
    if rule is None:
        raise ApiError(404, "not_found", "Commission rule not found")
    return rule


def lock_rule_for_catalog_assignment(session: Session, rule_id: int) -> CommissionRule:
    """Future active catalog writes must call this inside their write transaction."""
    rule = _lock_rule(session, rule_id)
    if not rule.active:
        raise ApiError(409, "rule_inactive", "Commission rule is inactive")
    return rule


def set_rule_active(session: Session, rule_id: int, *, active: bool, actor_user_id: int) -> CommissionRule:
    rule = _lock_rule(session, rule_id)
    if rule.active == active:
        return rule
    if not active:
        has_active_service = session.scalar(select(exists().where(
            Service.commission_rule_id == rule_id, Service.active.is_(True),
        )))
        has_active_product = session.scalar(select(exists().where(
            Product.commission_rule_id == rule_id, Product.active.is_(True),
        )))
        if has_active_service or has_active_product:
            raise ApiError(409, "rule_in_use", "Commission rule is used by active catalog items")
    rule.active = active
    session.add(AuditEvent(
        actor_user_id=actor_user_id, event_type="CommissionRuleStatusChanged",
        resource_type="commission_rule", resource_id=str(rule.id), outcome="Success",
        event_metadata={"active": active},
    ))
    session.flush()
    return rule
