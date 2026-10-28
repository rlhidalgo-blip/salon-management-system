"""Durable sale-attempt fences for the default-disabled reservation protocol."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CHAR, CheckConstraint, Computed, ForeignKey, Identity, Index, Integer, Text, TIMESTAMP, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


DIRECT_REFERENCE_SQL = (
    "CASE WHEN source = 'Direct' THEN 'DS-' || "
    "LPAD(id::text, GREATEST(12, LENGTH(id::text)), '0') ELSE NULL END"
)


class SaleAttempt(Base):
    __tablename__ = "sale_attempts"
    __table_args__ = (
        CheckConstraint("source IN ('Direct', 'Manual')", name="ck_sale_attempts_source"),
        CheckConstraint("state IN ('Reserved', 'Committed', 'Cancelled')", name="ck_sale_attempts_state"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_sale_attempts_request_hash"),
        CheckConstraint(
            "(source = 'Direct' AND manual_reference IS NULL) OR "
            "(source = 'Manual' AND manual_reference ~ '^PAPER-[0-9]{8}-[0-9]{3}$')",
            name="ck_sale_attempts_reference_source",
        ),
        CheckConstraint(
            "(state = 'Reserved' AND transaction_id IS NULL AND committed_at IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL) OR "
            "(state = 'Committed' AND transaction_id IS NOT NULL AND committed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL) OR "
            "(state = 'Cancelled' AND transaction_id IS NULL AND committed_at IS NULL "
            "AND cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL "
            "AND NULLIF(BTRIM(cancellation_reason), '') IS NOT NULL "
            "AND LENGTH(cancellation_reason) <= 500)",
            name="ck_sale_attempts_state_metadata",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_sale_attempts_user_key"),
        UniqueConstraint("direct_reference", name="uq_sale_attempts_direct_reference"),
        UniqueConstraint("manual_reference", name="uq_sale_attempts_manual_reference"),
        UniqueConstraint("transaction_id", name="uq_sale_attempts_transaction_id"),
        Index("uq_sale_attempts_one_reserved_user", "user_id", unique=True, postgresql_where=text("state = 'Reserved'")),
        Index("ix_sale_attempts_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'Reserved'"))
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    direct_reference: Mapped[str | None] = mapped_column(Text, Computed(DIRECT_REFERENCE_SQL, persisted=True))
    manual_reference: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
