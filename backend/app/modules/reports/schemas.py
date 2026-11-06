"""Daily report values derived from stored sale-item snapshots."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class StaffCommissionTotal(BaseModel):
    staff_id: int
    current_staff_name: str
    total_staff_commission: Decimal


class DailyReport(BaseModel):
    business_date: date
    gross_sales: Decimal
    cash_sales: Decimal
    gcash_sales: Decimal
    total_staff_commission: Decimal
    total_business_share: Decimal
    completed_transaction_count: int
    voided_transaction_count: int
    staff_commissions: list[StaffCommissionTotal]


class MonthlyStaffPerformance(BaseModel):
    staff_id: int
    current_staff_name: str
    attributed_sales: Decimal
    total_staff_commission: Decimal


class MonthlyReport(BaseModel):
    reporting_month: str
    gross_sales: Decimal
    cash_sales: Decimal
    gcash_sales: Decimal
    total_staff_commission: Decimal
    total_business_share: Decimal
    completed_transaction_count: int
    voided_transaction_count: int
    staff_performance: list[MonthlyStaffPerformance]
    unassigned_product_sales: Decimal


class WeekdaySalesRow(BaseModel):
    weekday_number: int  # ISO order: Monday=1 through Sunday=7.
    weekday: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    gross_sales: Decimal
    historical_gross_sales: Decimal
    verified_open_gross_sales: Decimal
    provisional_today_gross_sales: Decimal
    verified_open_days: int
    verified_closed_days: int
    unknown_days: int
    unconfirmed_planned_days: int
    closed_dates_with_sales: int
    average_gross_per_verified_open_day: Decimal | None


class WeekdayCoverage(BaseModel):
    historical_days: int
    verified_open_days: int
    verified_closed_days: int
    unknown_days: int
    unconfirmed_planned_days: int
    unverified_days: int
    closed_dates_with_sales: int
    incomplete_coverage: bool


class WeekdaySalesReport(BaseModel):
    from_date: date = Field(serialization_alias="from")
    through: date
    as_of: datetime
    coverage: WeekdayCoverage
    weekdays: list[WeekdaySalesRow]
