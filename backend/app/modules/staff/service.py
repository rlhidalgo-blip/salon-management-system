"""Small Staff operations; the API caller owns transaction boundaries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.staff.models import Staff


def list_staff(session: Session) -> list[Staff]:
    return list(session.scalars(select(Staff).order_by(Staff.id)))


def create_staff(session: Session, *, name: str, role: str) -> Staff:
    staff = Staff(name=name, role=role)
    session.add(staff)
    session.flush()
    return staff


def set_staff_active(session: Session, staff_id: int, *, active: bool) -> Staff:
    staff = session.get(Staff, staff_id)
    if staff is None:
        raise ApiError(404, "not_found", "Staff member not found")
    staff.active = active
    session.flush()
    return staff
