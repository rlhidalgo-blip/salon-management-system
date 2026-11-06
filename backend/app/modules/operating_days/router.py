"""Owner calendar reads and fenced writes."""

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner
from app.modules.operating_days.feature import require_calendar_writes_ready
from app.modules.operating_days.schemas import (
    BulkOpenResult, BulkOpenVerification, OperatingDayChange, OperatingDayPublic,
    OperatingDayUpdate, parse_business_date,
)
from app.modules.operating_days.service import bulk_verify_open, history, list_days, update_day


router = APIRouter(prefix="/api/v1/operating-days", tags=["operating days"])


def _date(value: str):
    try:
        return parse_business_date(value)
    except ValueError:
        raise ApiError(422, "invalid_business_date", "Use a valid YYYY-MM-DD date") from None


@router.get("", response_model=list[OperatingDayPublic])
def get_operating_days(response: Response, from_: str = Query(alias="from"), through: str = Query(),
                       _principal: Principal = Depends(require_owner),
                       session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return list_days(session, start=_date(from_), through=_date(through))


@router.put("/{business_date}", response_model=OperatingDayPublic,
            dependencies=[Depends(require_calendar_writes_ready)])
def put_operating_day(payload: OperatingDayUpdate, response: Response, business_date: str = Path(),
                      principal: Principal = Depends(require_owner),
                      session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return update_day(session, business_date=_date(business_date), payload=payload,
                          actor_user_id=principal.user_id)


@router.post("/bulk-verify-open", response_model=BulkOpenResult,
             dependencies=[Depends(require_calendar_writes_ready)])
def post_bulk_open(payload: BulkOpenVerification, response: Response,
                   principal: Principal = Depends(require_owner),
                   session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return bulk_verify_open(session, payload=payload, actor_user_id=principal.user_id)


@router.get("/{business_date}/history", response_model=list[OperatingDayChange])
def get_operating_day_history(response: Response, business_date: str = Path(),
                              limit: int = Query(default=50, ge=1, le=100),
                              _principal: Principal = Depends(require_owner),
                              session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return history(session, business_date=_date(business_date), limit=limit)
