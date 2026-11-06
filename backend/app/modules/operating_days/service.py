"""Owner calendar operations; the router owns commit and rollback."""

from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.operating_days.date_lock import lock_operating_date
from app.modules.operating_days.models import OperatingDay
from app.modules.operating_days.schemas import (
    BulkOpenResult, BulkOpenVerification, OperatingDayChange, OperatingDayPublic,
    OperatingDayUpdate,
)
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.service import _database_time


MANILA = ZoneInfo("Asia/Manila")
ZERO = Decimal("0.00")


def _today(session: Session) -> date:
    return _database_time(session).astimezone(MANILA).date()


def _sales_by_date(session: Session, dates: list[date]) -> dict[date, tuple[int, Decimal]]:
    if not dates:
        return {}
    rows = session.execute(
        select(Transaction.business_date, func.count(func.distinct(Transaction.id)),
               func.coalesce(func.sum(TransactionItem.selling_price), ZERO))
        .outerjoin(TransactionItem, TransactionItem.transaction_id == Transaction.id)
        .where(Transaction.status == "Completed", Transaction.business_date.in_(dates))
        .group_by(Transaction.business_date)
    ).all()
    return {day: (count, gross) for day, count, gross in rows}


def _public(day: date, record: OperatingDay | None,
            sales: tuple[int, Decimal] = (0, ZERO)) -> OperatingDayPublic:
    status = record.status if record else "Unknown"
    return OperatingDayPublic(
        business_date=day, status=status,
        closure_reason=record.closure_reason if record else None,
        version=record.version if record else 0,
        completed_transaction_count=sales[0], gross_sales=sales[1],
        inconsistency=status == "Closed" and sales[0] > 0,
    )


def list_days(session: Session, *, start: date, through: date) -> list[OperatingDayPublic]:
    span = (through - start).days + 1
    if span < 1 or span > 90:
        raise ApiError(422, "invalid_date_range", "Choose a range of 1 to 90 dates")
    dates = [start + timedelta(days=offset) for offset in range(span)]
    records = {row.business_date: row for row in session.scalars(
        select(OperatingDay).where(OperatingDay.business_date >= start,
                                   OperatingDay.business_date <= through)
    )}
    sales = _sales_by_date(session, dates)
    return [_public(day, records.get(day), sales.get(day, (0, ZERO))) for day in dates]


def _current_locked(session: Session, business_date: date) -> OperatingDay | None:
    return session.scalar(select(OperatingDay).where(OperatingDay.business_date == business_date)
                          .with_for_update().execution_options(populate_existing=True))


def _expect_version(record: OperatingDay | None, expected: int) -> None:
    if (record.version if record else 0) != expected:
        raise ApiError(409, "operating_day_changed", "Operating date changed; refresh before retrying")


def _has_completed(session: Session, business_date: date) -> bool:
    return session.scalar(select(Transaction.id).where(
        Transaction.business_date == business_date, Transaction.status == "Completed"
    ).limit(1)) is not None


def _change(session: Session, *, business_date: date, record: OperatingDay | None,
            status: str, reason: str | None, actor_user_id: int, bulk: bool) -> OperatingDay:
    before = {
        "previous_status": record.status if record else "Unknown",
        "previous_reason": record.closure_reason if record else None,
        "previous_version": record.version if record else 0,
    }
    now = _database_time(session)
    if record is None:
        record = OperatingDay(
            business_date=business_date, status=status, closure_reason=reason,
            created_by_user_id=actor_user_id, updated_by_user_id=actor_user_id,
            created_at=now, updated_at=now, version=1,
        )
        session.add(record)
    else:
        record.status = status
        record.closure_reason = reason
        record.updated_by_user_id = actor_user_id
        record.updated_at = now
        record.version += 1
    session.flush()
    session.add(AuditEvent(
        actor_user_id=actor_user_id, event_type="OperatingDayChanged",
        resource_type="operating_day", resource_id=business_date.isoformat(),
        outcome="Success", occurred_at=now,
        event_metadata={**before, "status": status, "closure_reason": reason,
                        "version": record.version, "bulk": bulk},
    ))
    session.flush()
    return record


def update_day(session: Session, *, business_date: date, payload: OperatingDayUpdate,
               actor_user_id: int) -> OperatingDayPublic:
    lock_operating_date(session, business_date)
    record = _current_locked(session, business_date)
    _expect_version(record, payload.expected_version)
    today = _today(session)
    if (payload.status == "PlannedClosed" and business_date <= today
            and (record is None or record.status != "PlannedClosed")):
        raise ApiError(422, "invalid_business_date", "New plans require a future date")
    if payload.status in ("Open", "Closed") and business_date > today:
        raise ApiError(422, "invalid_business_date", "Future dates cannot be verified")
    if payload.status == "Closed" and _has_completed(session, business_date):
        raise ApiError(409, "completed_sales_on_date", "Completed sales exist on this date")
    if record is not None and (record.status, record.closure_reason) == (payload.status, payload.closure_reason):
        return _public(business_date, record, _sales_by_date(session, [business_date]).get(business_date, (0, ZERO)))
    record = _change(session, business_date=business_date, record=record, status=payload.status,
                     reason=payload.closure_reason, actor_user_id=actor_user_id, bulk=False)
    return _public(business_date, record, _sales_by_date(session, [business_date]).get(business_date, (0, ZERO)))


def bulk_verify_open(session: Session, *, payload: BulkOpenVerification,
                     actor_user_id: int) -> BulkOpenResult:
    dates = sorted(item.business_date for item in payload.dates)
    today = _today(session)
    if dates[-1] >= today:
        raise ApiError(422, "invalid_business_date", "Bulk verification requires historical dates")
    for business_date in dates:
        lock_operating_date(session, business_date)
    expected = {item.business_date: item.expected_version for item in payload.dates}
    records: dict[date, OperatingDay | None] = {}
    for business_date in dates:
        record = _current_locked(session, business_date)
        _expect_version(record, expected[business_date])
        if record is not None and record.status != "Unknown":
            raise ApiError(409, "operating_day_changed", "Only Unknown dates can be bulk verified")
        records[business_date] = record
    changed = [
        _change(session, business_date=business_date, record=records[business_date],
                status="Open", reason=None, actor_user_id=actor_user_id, bulk=True)
        for business_date in dates
    ]
    sales = _sales_by_date(session, dates)
    return BulkOpenResult(changed_count=len(changed), dates=[
        _public(day, record, sales.get(day, (0, ZERO))) for day, record in zip(dates, changed)
    ])


def history(session: Session, *, business_date: date, limit: int) -> list[OperatingDayChange]:
    rows = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "OperatingDayChanged",
        AuditEvent.resource_type == "operating_day",
        AuditEvent.resource_id == business_date.isoformat(),
    ).order_by(AuditEvent.id.desc()).limit(limit)).all()
    return [OperatingDayChange(actor_user_id=row.actor_user_id, occurred_at=row.occurred_at,
                               **row.event_metadata) for row in rows]
