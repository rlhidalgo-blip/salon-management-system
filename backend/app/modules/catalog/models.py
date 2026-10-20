from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Identity, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.commissions.models import CommissionRule


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (CheckConstraint("current_price > 0", name="ck_services_current_price"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    allows_variable_price: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    commission_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission_rules.id", ondelete="RESTRICT"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    commission_rule: Mapped[CommissionRule] = relationship(back_populates="services")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("current_price > 0", name="ck_products_current_price"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission_rules.id", ondelete="RESTRICT"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    commission_rule: Mapped[CommissionRule] = relationship(back_populates="products")
