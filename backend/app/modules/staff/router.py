"""Owner-only Staff administration; no name/role edits or delete routes."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner
from app.modules.staff.schemas import StaffCreate, StaffPublic, StaffStatus
from app.modules.staff.service import create_staff, list_staff, set_staff_active


router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


@router.get("", response_model=list[StaffPublic])
def get_staff(
    _principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> list[StaffPublic]:
    with session.begin():
        return [StaffPublic.model_validate(staff) for staff in list_staff(session)]


@router.post("", response_model=StaffPublic, status_code=201)
def post_staff(
    payload: StaffCreate,
    _principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> StaffPublic:
    with session.begin():
        staff = create_staff(session, name=payload.name, role=payload.role)
        result = StaffPublic.model_validate(staff)
    return result


@router.patch("/{staff_id}/status", response_model=StaffPublic)
def patch_staff_status(
    payload: StaffStatus,
    staff_id: int = Path(gt=0),
    _principal: Principal = Depends(require_owner),
    session: Session = Depends(get_db_session),
) -> StaffPublic:
    with session.begin():
        staff = set_staff_active(session, staff_id, active=payload.active)
        result = StaffPublic.model_validate(staff)
    return result
