"""Role-specific, deliberately limited transaction-history responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=500, description="Required free-text reason, up to 500 characters.")

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Void reason is required")
        return value


class CashierHistoryRow(BaseModel):
    id: int
    date_time: datetime
    business_date: date
    status: Literal["Completed", "Voided"]
    payment_method: Literal["Cash", "GCash"]
    gross_sales: Decimal
    total_staff_commission: Decimal
    total_business_share: Decimal


class CashierHistoryPage(BaseModel):
    items: list[CashierHistoryRow]
    next_cursor: str | None


class CashierHistoryItem(BaseModel):
    id: int
    item_name_snapshot: str
    selling_price: Decimal
    staff_id: int | None
    staff_name: str | None
    service_id: int | None
    product_id: int | None
    commission_type_snapshot: str | None
    commission_value_snapshot: Decimal | None
    staff_commission: Decimal
    business_share: Decimal


class CashierHistoryDetail(CashierHistoryRow):
    gcash_reference: str | None
    items: list[CashierHistoryItem]


class OwnerHistoryDetail(CashierHistoryDetail):
    created_at: datetime
    recorded_by_user_id: int
    entry_source: str
    manual_reference: str | None
    void_reason: str | None
    voided_by_user_id: int | None
    voided_at: datetime | None
