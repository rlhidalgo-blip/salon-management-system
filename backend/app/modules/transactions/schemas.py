"""Direct-sale request and safe historical snapshot responses."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PRICE_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?$")


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
