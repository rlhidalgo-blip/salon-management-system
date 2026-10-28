"""Strict internal contracts; no sale payload or request digest in discovery responses."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.transactions.schemas import ManualSaleCreate, SaleCreate


class DirectReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["Direct"]
    sale: SaleCreate


class ManualReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["Manual"]
    sale: ManualSaleCreate


ReservationRequest = Annotated[DirectReservation | ManualReservation, Field(discriminator="source")]


class AttemptPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    idempotency_key: UUID
    source: Literal["Direct", "Manual"]
    state: Literal["Reserved", "Committed", "Cancelled"]
    direct_reference: str | None
    manual_reference: str | None
    transaction_id: int | None
    created_at: datetime
    committed_at: datetime | None
    cancelled_at: datetime | None


class AttemptInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recording_user_id: int = Field(strict=True, gt=0)
    created_from: datetime | None = None
    created_before: datetime | None = None
    reference: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=50, strict=True, ge=1, le=100)
    before_id: int | None = Field(default=None, strict=True, gt=0)

    @field_validator("reference")
    @classmethod
    def normalize_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not value or not (value.startswith("DS-") or value.startswith("PAPER-")):
            raise ValueError("Invalid attempt reference")
        return value

    @model_validator(mode="after")
    def valid_range(self):
        if self.created_from and self.created_from.utcoffset() is None:
            raise ValueError("created_from requires a timezone offset")
        if self.created_before and self.created_before.utcoffset() is None:
            raise ValueError("created_before requires a timezone offset")
        if self.created_from and self.created_before and self.created_from >= self.created_before:
            raise ValueError("Invalid time range")
        return self


class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    evidence_verified: Literal[True]

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Cancellation reason is required")
        return value
