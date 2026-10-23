"""Read-only daily financial reporting from one consistent SQL statement."""

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.staff.models import Staff
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.transactions.service import _database_time
from app.modules.reports.schemas import DailyReport, StaffCommissionTotal


MANILA = ZoneInfo("Asia/Manila")
ZERO = Decimal("0.00")


def daily_report(session: Session, *, role: str, business_date: date | None) -> DailyReport:
    """Use one SQL statement for all financial values and counts.

    The first query obtains trusted database time for the access decision. The
    aggregation itself is one PostgreSQL statement, so a concurrent void cannot
    split summary values from the staff breakdown across snapshots.
    """
    today = _database_time(session).astimezone(MANILA).date()
    chosen = business_date or today
    if role == "Cashier" and chosen != today:
        raise ApiError(403, "forbidden", "Report date is not available")
    if chosen > today:
        raise ApiError(422, "invalid_business_date", "Report date cannot be in the future")

    day_transactions = (
        select(Transaction.id, Transaction.status, Transaction.payment_method)
        .where(Transaction.business_date == chosen)
        .cte("day_transactions")
    )
    counts = (
        select(
            func.count().filter(day_transactions.c.status == "Completed").label("completed_count"),
            func.count().filter(day_transactions.c.status == "Voided").label("voided_count"),
        )
        .select_from(day_transactions)
        .cte("status_counts")
    )
    completed_items = (
        select(
            day_transactions.c.payment_method,
            TransactionItem.staff_id,
            TransactionItem.selling_price,
            TransactionItem.staff_commission,
            TransactionItem.business_share,
        )
        .join(TransactionItem, TransactionItem.transaction_id == day_transactions.c.id)
        .where(day_transactions.c.status == "Completed")
        .cte("completed_items")
    )
    totals = (
        select(
            func.coalesce(func.sum(completed_items.c.selling_price), ZERO).label("gross"),
            func.coalesce(func.sum(case((completed_items.c.payment_method == "Cash",
                                         completed_items.c.selling_price), else_=ZERO)), ZERO).label("cash"),
            func.coalesce(func.sum(case((completed_items.c.payment_method == "GCash",
                                         completed_items.c.selling_price), else_=ZERO)), ZERO).label("gcash"),
            func.coalesce(func.sum(completed_items.c.staff_commission), ZERO).label("commission"),
            func.coalesce(func.sum(completed_items.c.business_share), ZERO).label("business"),
        )
        .select_from(completed_items)
        .cte("financial_totals")
    )
    staff_totals = (
        select(
            completed_items.c.staff_id,
            func.sum(completed_items.c.staff_commission).label("commission"),
        )
        .where(completed_items.c.staff_id.is_not(None))
        .group_by(completed_items.c.staff_id)
        .cte("staff_totals")
    )
    statement = (
        select(
            counts.c.completed_count,
            counts.c.voided_count,
            totals.c.gross,
            totals.c.cash,
            totals.c.gcash,
            totals.c.commission,
            totals.c.business,
            staff_totals.c.staff_id,
            Staff.name.label("current_staff_name"),
            staff_totals.c.commission.label("staff_commission"),
        )
        .select_from(counts)
        .join(totals, true())
        .outerjoin(staff_totals, true())
        .outerjoin(Staff, Staff.id == staff_totals.c.staff_id)
        .order_by(staff_totals.c.staff_id)
    )
    rows = session.execute(statement).all()
    summary = rows[0]
    staff_commissions = [
        StaffCommissionTotal(
            staff_id=row.staff_id,
            current_staff_name=row.current_staff_name,
            total_staff_commission=row.staff_commission,
        )
        for row in rows if row.staff_id is not None
    ]
    return DailyReport(
        business_date=chosen,
        gross_sales=summary.gross,
        cash_sales=summary.cash,
        gcash_sales=summary.gcash,
        total_staff_commission=summary.commission,
        total_business_share=summary.business,
        completed_transaction_count=summary.completed_count,
        voided_transaction_count=summary.voided_count,
        staff_commissions=staff_commissions,
    )
