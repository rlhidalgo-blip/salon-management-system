"""Owner-only commission-rule configuration."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner
from app.modules.commissions.schemas import CommissionRuleCreate, CommissionRulePublic, CommissionRuleStatus
from app.modules.commissions.service import create_rule, list_rules, set_rule_active


router = APIRouter(prefix="/api/v1/commission-rules", tags=["commission-rules"])


@router.get("", response_model=list[CommissionRulePublic])
def get_commission_rules(
    _principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> list[CommissionRulePublic]:
    with session.begin():
        return [CommissionRulePublic.model_validate(rule) for rule in list_rules(session)]


@router.post("", response_model=CommissionRulePublic, status_code=201)
def post_commission_rule(
    payload: CommissionRuleCreate,
    principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> CommissionRulePublic:
    with session.begin():
        rule = create_rule(session, name=payload.name, type=payload.type, value=payload.value,
                           actor_user_id=principal.user_id)
        result = CommissionRulePublic.model_validate(rule)
    return result


@router.patch("/{rule_id}/status", response_model=CommissionRulePublic)
def patch_commission_rule_status(
    payload: CommissionRuleStatus,
    rule_id: int = Path(gt=0),
    principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> CommissionRulePublic:
    with session.begin():
        rule = set_rule_active(session, rule_id, active=payload.active, actor_user_id=principal.user_id)
        result = CommissionRulePublic.model_validate(rule)
    return result
