from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    TIMESTAMP,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.catalog.models import Product, Service
    from app.modules.staff.models import Staff
    from app.modules.users.models import User


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("payment_method IN ('Cash', 'GCash')", name="ck_transactions_payment_method"),
        CheckConstraint(
            "(payment_method = 'Cash' AND gcash_reference IS NULL) OR "
            "(payment_method = 'GCash' AND NULLIF(BTRIM(gcash_reference), '') IS NOT NULL)",
            name="ck_transactions_gcash_reference",
        ),
        CheckConstraint("status IN ('Completed', 'Voided')", name="ck_transactions_status"),
        CheckConstraint(
            "(status = 'Completed' AND void_reason IS NULL AND voided_by_user_id IS NULL AND voided_at IS NULL) OR "
            "(status = 'Voided' AND NULLIF(BTRIM(void_reason), '') IS NOT NULL "
            "AND voided_by_user_id IS NOT NULL AND voided_at IS NOT NULL)",
            name="ck_transactions_void_metadata",
        ),
        CheckConstraint("entry_source IN ('Direct', 'Manual')", name="ck_transactions_entry_source"),
        CheckConstraint(
            "(entry_source = 'Direct' AND manual_reference IS NULL) OR "
            "(entry_source = 'Manual' AND NULLIF(BTRIM(manual_reference), '') IS NOT NULL)",
            name="ck_transactions_manual_reference",
        ),
        Index("ix_transactions_date_time", "date_time"),
        Index("ix_transactions_business_date", "business_date"),
        Index("ix_transactions_recorded_by_user_id", "recorded_by_user_id"),
        Index(
            "uq_transactions_manual_reference",
            "manual_reference",
            unique=True,
            postgresql_where=text("manual_reference IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    date_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    recorded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    entry_source: Mapped[str] = mapped_column(Text, nullable=False)
    manual_reference: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    gcash_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'Completed'"))
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    recorded_by: Mapped[User] = relationship(foreign_keys=[recorded_by_user_id])
    voided_by: Mapped[User | None] = relationship(foreign_keys=[voided_by_user_id])
    items: Mapped[list[TransactionItem]] = relationship(back_populates="transaction")


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    __table_args__ = (
        CheckConstraint(
            "(service_id IS NOT NULL AND product_id IS NULL) OR "
            "(service_id IS NULL AND product_id IS NOT NULL)",
            name="ck_transaction_items_one_item_type",
        ),
        CheckConstraint("service_id IS NULL OR staff_id IS NOT NULL", name="ck_transaction_items_service_staff"),
        CheckConstraint("selling_price > 0", name="ck_transaction_items_selling_price"),
        CheckConstraint("staff_commission >= 0", name="ck_transaction_items_staff_commission"),
        CheckConstraint("business_share >= 0", name="ck_transaction_items_business_share"),
        CheckConstraint("staff_commission <= selling_price", name="ck_transaction_items_commission_limit"),
        CheckConstraint(
            "staff_commission + business_share = selling_price",
            name="ck_transaction_items_financial_total",
        ),
        CheckConstraint(
            "(commission_type_snapshot IS NULL AND commission_value_snapshot IS NULL) OR "
            "(commission_type_snapshot IN ('Percentage', 'Fixed') "
            "AND commission_value_snapshot IS NOT NULL AND commission_value_snapshot > 0 "
            "AND (commission_type_snapshot <> 'Percentage' OR commission_value_snapshot <= 100))",
            name="ck_transaction_items_commission_snapshot",
        ),
        CheckConstraint(
            "(service_id IS NOT NULL AND commission_type_snapshot IS NOT NULL "
            "AND commission_type_snapshot = 'Percentage') OR "
            "(product_id IS NOT NULL AND staff_id IS NOT NULL AND commission_type_snapshot IS NOT NULL "
            "AND commission_type_snapshot = 'Fixed') OR "
            "(product_id IS NOT NULL AND staff_id IS NULL AND commission_type_snapshot IS NULL "
            "AND commission_value_snapshot IS NULL AND staff_commission = 0)",
            name="ck_transaction_items_commission_assignment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False)
    service_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("services.id", ondelete="RESTRICT"))
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.id", ondelete="RESTRICT"))
    staff_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("staff.id", ondelete="RESTRICT"))
    item_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission_type_snapshot: Mapped[str | None] = mapped_column(Text)
    commission_value_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    staff_commission: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    business_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="items")
    service: Mapped[Service | None] = relationship()
    product: Mapped[Product | None] = relationship()
    staff: Mapped[Staff | None] = relationship()
