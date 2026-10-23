"""Authorized read-only daily reporting endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner_or_cashier
from app.modules.reports.schemas import DailyReport
from app.modules.reports.service import daily_report


router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/daily", response_model=DailyReport)
def get_daily_report(response: Response, business_date: date | None = None,
                     principal: Principal = Depends(require_owner_or_cashier),
                     session: Session = Depends(get_db_session)) -> DailyReport:
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return daily_report(session, role=principal.role, business_date=business_date)
