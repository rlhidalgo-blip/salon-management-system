"""One transaction-scoped calendar lock for calendar and sale writers."""

import hashlib
from datetime import date

from sqlalchemy import BigInteger, bindparam, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.operating_days.models import OperatingDay


def lock_operating_date(session: Session, business_date: date, *, for_sale: bool = False) -> None:
    digest = hashlib.sha256(f"calendar:{business_date.isoformat()}".encode("ascii")).digest()
    lock_id = int.from_bytes(digest[:8], "big", signed=True)
    statement = text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
        bindparam("lock_id", type_=BigInteger)
    )
    try:
        session.execute(text("SET LOCAL lock_timeout = '3s'"))
        session.execute(statement, {"lock_id": lock_id})
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in ("55P03", "57014", "40P01"):
            if for_sale:
                raise ApiError(503, "sale_outcome_uncertain",
                               "Sale outcome is uncertain; check the same key before retrying") from None
            raise ApiError(503, "calendar_busy", "Calendar date is busy; refresh and retry") from None
        raise


def require_sale_date_not_closed(session: Session, business_date: date) -> None:
    """Call only after acquiring this date's advisory lock in the same transaction."""
    status = session.scalar(select(OperatingDay.status).where(OperatingDay.business_date == business_date))
    if status == "Closed":
        raise ApiError(409, "business_date_closed", "Salon is verified Closed on this business date")
