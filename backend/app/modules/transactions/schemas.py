"""Direct-sale request and safe historical snapshot responses."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PRICE_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$")
PAPER_REFERENCE_PATTERN = re.compile(r"^PAPER-([0-9]{8})-([0-9]{3})$")


class SaleItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: int | None = Field(default=None, strict=True, gt=0)
    product_id: int | None = Field(default=None, strict=True, gt=0)
    staff_id: int | None = Field(default=None, strict=True, gt=0)
    selling_price: Decimal

    @field_validator("selling_price", mode="before")
    @classmethod
    def price_as_decimal_string(cls, value):
        if not isinstance(value, str) or not PRICE_PATTERN.fullmatch(value) or Decimal(value) <= 0:
            raise ValueError("Selling price must be a positive decimal string with at most two places")
        return value

    @model_validator(mode="after")
    def exactly_one_catalog_item(self):
        if (self.service_id is None) == (self.product_id is None):
            raise ValueError("Provide exactly one service_id or product_id")
        if self.service_id is not None and self.staff_id is None:
            raise ValueError("Service items require staff_id")
        return self


class SaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_method: Literal["Cash", "GCash"]
    gcash_reference: str | None = None
    items: list[SaleItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def payment_reference(self):
        if self.payment_method == "Cash" and self.gcash_reference is not None:
            raise ValueError("Cash sales cannot have a GCash reference")
        if self.payment_method == "GCash":
            if self.gcash_reference is None or not self.gcash_reference.strip():
                raise ValueError("GCash reference is required")
            self.gcash_reference = self.gcash_reference.strip()
        return self


class ManualSaleItemCreate(SaleItemCreate):
    item_name_snapshot: str
    commission_type_snapshot: Literal["Percentage", "Fixed"] | None = None
    commission_value_snapshot: Decimal | None = None

    @field_validator("item_name_snapshot")
    @classmethod
    def nonblank_item_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Original item name is required")
        return value

    @field_validator("commission_value_snapshot", mode="before")
    @classmethod
    def commission_as_decimal_string(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or not PRICE_PATTERN.fullmatch(value) or Decimal(value) <= 0:
            raise ValueError("Commission value must be a positive decimal string with at most two places")
        return value

    @model_validator(mode="after")
    def historical_commission_assignment(self):
        expected = "Percentage" if self.service_id is not None else ("Fixed" if self.staff_id is not None else None)
        if self.commission_type_snapshot != expected or (self.commission_value_snapshot is None) != (expected is None):
            raise ValueError("Historical commission type/value must match the credited item")
        if expected == "Percentage" and self.commission_value_snapshot > 100:
            raise ValueError("Percentage commission cannot exceed 100")
        return self


class ManualSaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_time: datetime
    manual_reference: str
    verified_against_paper: bool = Field(strict=True)
    payment_method: Literal["Cash", "GCash"]
    gcash_reference: str | None = None
    items: list[ManualSaleItemCreate] = Field(min_length=1)

    @field_validator("date_time", mode="before")
    @classmethod
    def offset_timestamp_required(cls, value):
        if not isinstance(value, str) or not re.search(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$", value):
            raise ValueError("Original sale time must include a timezone offset")
        return value

    @field_validator("manual_reference")
    @classmethod
    def normalize_paper_reference(cls, value: str) -> str:
        value = value.strip().upper()
        match = PAPER_REFERENCE_PATTERN.fullmatch(value)
        if len(value) > 40 or match is None or match.group(2) == "000":
            raise ValueError("Paper reference must use PAPER-YYYYMMDD-NNN (001-999)")
        try:
            date.fromisoformat(f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}")
        except ValueError:
            raise ValueError("Paper reference must contain a valid date") from None
        return value

    @model_validator(mode="after")
    def manual_payment_and_evidence(self):
        if not self.verified_against_paper:
            raise ValueError("Original paper record and historical values must be verified")
        if self.date_time.utcoffset() is None:
            raise ValueError("Original sale time must include a timezone offset")
        if self.payment_method == "Cash" and self.gcash_reference is not None:
            raise ValueError("Cash sales cannot have a GCash reference")
        if self.payment_method == "GCash":
            if self.gcash_reference is None or not self.gcash_reference.strip():
                raise ValueError("GCash reference is required")
            self.gcash_reference = self.gcash_reference.strip()
        return self


class SaleItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int | None
    product_id: int | None
    staff_id: int | None
    item_name_snapshot: str
    selling_price: Decimal
    commission_type_snapshot: str | None
    commission_value_snapshot: Decimal | None
    staff_commission: Decimal
    business_share: Decimal


class SalePublic(BaseModel):
    id: int
    date_time: datetime
    business_date: date
    recorded_by_user_id: int
    payment_method: str
    gcash_reference: str | None
    status: str
    items: list[SaleItemPublic]
    gross_sales: Decimal
    total_staff_commission: Decimal
    total_business_share: Decimal


class SaleKeyStatus(BaseModel):
    status: Literal["committed", "processing", "not_committed_at_check"]
    sale: SalePublic | None = None


class SaleAcknowledgment(BaseModel):
    status: Literal["committed"]
    recording_user_id: int
    idempotency_key: str
    sale: SalePublic
