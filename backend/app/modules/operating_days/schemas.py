from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OperatingStatus = Literal["Open", "Closed", "Unknown", "PlannedClosed"]


def parse_business_date(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-" or not (
        value[:4] + value[5:7] + value[8:]
    ).isascii() or not (value[:4] + value[5:7] + value[8:]).isdigit():
        raise ValueError("Date must use YYYY-MM-DD")
    return date.fromisoformat(value)


class OperatingDayUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OperatingStatus
    closure_reason: str | None = None
    expected_version: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_reason(self):
        if self.status in ("Closed", "PlannedClosed"):
            if self.closure_reason is None or not self.closure_reason.strip():
                raise ValueError("Closure reason is required")
            self.closure_reason = self.closure_reason.strip()
            if len(self.closure_reason) > 500:
                raise ValueError("Closure reason is too long")
        elif self.closure_reason is not None:
            raise ValueError("Reason is only allowed for a closure")
        return self


class BulkDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_date: date
    expected_version: int = Field(strict=True, ge=0)

    @field_validator("business_date", mode="before")
    @classmethod
    def exact_date(cls, value):
        return parse_business_date(value)


class BulkOpenVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dates: list[BulkDate] = Field(min_length=1, max_length=90)

    @model_validator(mode="after")
    def unique_dates(self):
        if len({item.business_date for item in self.dates}) != len(self.dates):
            raise ValueError("Duplicate business date")
        return self


class OperatingDayPublic(BaseModel):
    business_date: date
    status: OperatingStatus
    closure_reason: str | None
    version: int
    completed_transaction_count: int
    gross_sales: Decimal
    inconsistency: bool


class BulkOpenResult(BaseModel):
    changed_count: int
    dates: list[OperatingDayPublic]


class OperatingDayChange(BaseModel):
    actor_user_id: int
    occurred_at: datetime
    previous_status: OperatingStatus
    previous_reason: str | None
    previous_version: int
    status: OperatingStatus
    closure_reason: str | None
    version: int
    bulk: bool
