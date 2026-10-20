from __future__ import annotations

from typing import TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Identity, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.catalog.models import Product, Service


class CommissionRule(Base):
    __tablename__ = "commission_rules"
    __table_args__ = (
        CheckConstraint("type IN ('Percentage', 'Fixed')", name="ck_commission_rules_type"),
        CheckConstraint("value > 0 AND (type <> 'Percentage' OR value <= 100)", name="ck_commission_rules_value"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    services: Mapped[list[Service]] = relationship(back_populates="commission_rule")
    products: Mapped[list[Product]] = relationship(back_populates="commission_rule")
