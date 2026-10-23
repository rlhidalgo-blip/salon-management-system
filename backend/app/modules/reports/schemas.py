"""Daily report values derived from stored sale-item snapshots."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


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
