"""Date-scoped history and atomic Owner voiding. The router owns commits."""

import base64
import binascii
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.audit.models import AuditEvent
from app.modules.staff.models import Staff
from app.modules.transactions.history_schemas import (
    CashierHistoryDetail, CashierHistoryItem, CashierHistoryPage, CashierHistoryRow,
    OwnerHistoryDetail,
)
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.service import _database_time


MANILA = ZoneInfo("Asia/Manila")
CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _today(session: Session) -> date:
    return _database_time(session).astimezone(MANILA).date()


def _allowed_date(session: Session, *, role: str, requested: date | None) -> date:
    today = _today(session)
    chosen = requested or today
    if role == "Cashier" and chosen != today:
        raise ApiError(403, "forbidden", "Transaction date is not available")
    return chosen


def _encode_cursor(when: datetime, row_id: int, business_date: date) -> str:
    # PostgreSQL TIMESTAMPTZ is aware; SQLite's test adapter drops its offset.
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    payload = json.dumps([when.isoformat(), row_id, business_date.isoformat(), "asc"], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, business_date: date) -> tuple[datetime, int]:
    if len(cursor) > 256 or not CURSOR_PATTERN.fullmatch(cursor):
        raise ApiError(422, "invalid_cursor", "Invalid history cursor")
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if (not isinstance(values, list) or len(values) != 4 or
                type(values[1]) is not int or values[1] <= 0 or
                values[2] != business_date.isoformat() or values[3] != "asc"):
            raise ValueError
        when = datetime.fromisoformat(values[0])
        if when.tzinfo is None:
            raise ValueError
        return when, values[1]
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise ApiError(422, "invalid_cursor", "Invalid history cursor") from None


def list_history(session: Session, *, role: str, business_date: date | None,
                 limit: int, cursor: str | None) -> CashierHistoryPage:
    chosen = _allowed_date(session, role=role, requested=business_date)
    columns = (Transaction.id, Transaction.date_time, Transaction.business_date,
               Transaction.status, Transaction.payment_method,
               func.sum(TransactionItem.selling_price).label("gross_sales"),
               func.sum(TransactionItem.staff_commission).label("total_staff_commission"),
               func.sum(TransactionItem.business_share).label("total_business_share"))
    statement = (select(*columns).join(TransactionItem, TransactionItem.transaction_id == Transaction.id)
                 .where(Transaction.business_date == chosen)
                 .group_by(Transaction.id, Transaction.date_time, Transaction.business_date,
                           Transaction.status, Transaction.payment_method)
                 .order_by(Transaction.date_time.asc(), Transaction.id.asc()).limit(limit + 1))
    if cursor:
        when, row_id = _decode_cursor(cursor, chosen)
        statement = statement.where(or_(Transaction.date_time > when,
                                        and_(Transaction.date_time == when, Transaction.id > row_id)))
    rows = session.execute(statement).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].date_time, rows[-1].id, chosen) if has_more else None
    return CashierHistoryPage(items=[CashierHistoryRow.model_validate(row._mapping) for row in rows],
                              next_cursor=next_cursor)


def get_history_detail(session: Session, transaction_id: int, *, role: str) -> CashierHistoryDetail | OwnerHistoryDetail:
    if role == "Owner":
        transaction = session.get(Transaction, transaction_id)
        if transaction is None:
            raise ApiError(404, "not_found", "Transaction not found")
        header = transaction
    else:
        today = _today(session)
        header = session.execute(select(
            Transaction.id, Transaction.date_time, Transaction.business_date,
            Transaction.status, Transaction.payment_method, Transaction.gcash_reference,
        ).where(Transaction.id == transaction_id, Transaction.business_date == today)).one_or_none()
        if header is None:
            raise ApiError(404, "not_found", "Transaction not found")

    item_statement = (select(TransactionItem.id, TransactionItem.item_name_snapshot,
                             TransactionItem.selling_price, TransactionItem.staff_id,
                             Staff.name.label("staff_name"), TransactionItem.service_id,
                             TransactionItem.product_id, TransactionItem.commission_type_snapshot,
                             TransactionItem.commission_value_snapshot,
                             TransactionItem.staff_commission, TransactionItem.business_share)
                      .outerjoin(Staff, Staff.id == TransactionItem.staff_id)
                      .where(TransactionItem.transaction_id == transaction_id)
                      .order_by(TransactionItem.id))
    items = [CashierHistoryItem.model_validate(row._mapping)
             for row in session.execute(item_statement)]

    gross = sum((item.selling_price for item in items), Decimal("0.00"))
    common = dict(id=header.id, date_time=header.date_time, business_date=header.business_date,
                  status=header.status, payment_method=header.payment_method,
                  gross_sales=gross,
                  total_staff_commission=sum((item.staff_commission for item in items), Decimal("0.00")),
                  total_business_share=sum((item.business_share for item in items), Decimal("0.00")),
                  gcash_reference=header.gcash_reference, items=items)
    if role == "Owner":
        return OwnerHistoryDetail(
            **common,
            created_at=header.created_at, recorded_by_user_id=header.recorded_by_user_id,
            entry_source=header.entry_source, manual_reference=header.manual_reference,
            void_reason=header.void_reason, voided_by_user_id=header.voided_by_user_id,
            voided_at=header.voided_at,
        )
    return CashierHistoryDetail(**common)


def record_rejected_void(session: Session, *, actor_user_id: int, transaction_id: int) -> None:
    """Write only a scoped failure event; no transaction row is touched."""
    session.add(AuditEvent(actor_user_id=actor_user_id, event_type="TransactionVoid",
                           resource_type="transaction", resource_id=str(transaction_id),
                           outcome="Failure", occurred_at=_database_time(session)))
    session.flush()


def void_transaction(session: Session, *, transaction_id: int, reason: str,
                     actor_user_id: int) -> bool:
    """Return False for already Voided, persisting only its failure audit event."""
    transaction = session.scalar(select(Transaction).where(Transaction.id == transaction_id).with_for_update())
    if transaction is None:
        raise ApiError(404, "not_found", "Transaction not found")
    if transaction.status == "Voided":
        record_rejected_void(session, actor_user_id=actor_user_id, transaction_id=transaction_id)
        return False
    if transaction.status != "Completed":
        raise ApiError(409, "invalid_status", "Transaction cannot be voided")
    void_time = _database_time(session)
    transaction.status = "Voided"
    transaction.void_reason = reason
    transaction.voided_by_user_id = actor_user_id
    transaction.voided_at = void_time
    session.add(AuditEvent(actor_user_id=actor_user_id, event_type="TransactionVoid",
                           resource_type="transaction", resource_id=str(transaction_id),
                           outcome="Success", occurred_at=void_time))
    session.flush()
    return True
