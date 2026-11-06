"""Authorized read-only daily reporting endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner, require_owner_or_cashier
from app.modules.operating_days.schemas import parse_business_date
from app.modules.reports.schemas import DailyReport, MonthlyReport, WeekdaySalesReport
from app.modules.reports.service import daily_report, monthly_report, weekday_sales_report


router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/daily", response_model=DailyReport)
def get_daily_report(response: Response, business_date: date | None = None,
                     principal: Principal = Depends(require_owner_or_cashier),
                     session: Session = Depends(get_db_session)) -> DailyReport:
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return daily_report(session, role=principal.role, business_date=business_date)


@router.get("/monthly", response_model=MonthlyReport)
def get_monthly_report(response: Response, month: str | None = None,
                       _principal: Principal = Depends(require_owner),
                       session: Session = Depends(get_db_session)) -> MonthlyReport:
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return monthly_report(session, month=month)


@router.get("/weekday-sales", response_model=WeekdaySalesReport)
def get_weekday_sales_report(response: Response, from_: str = Query(alias="from"),
                             through: str = Query(),
                             _principal: Principal = Depends(require_owner),
                             session: Session = Depends(get_db_session)) -> WeekdaySalesReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        start = parse_business_date(from_)
        end = parse_business_date(through)
    except ValueError:
        raise ApiError(422, "invalid_business_date", "Use valid YYYY-MM-DD dates") from None
    with session.begin():
        return weekday_sales_report(session, start=start, through=end)
