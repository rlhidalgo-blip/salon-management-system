from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CHAR, ForeignKey, Identity, Index, Integer, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.transactions.models import Transaction
    from app.modules.users.models import User


class SaleIdempotency(Base):
    __tablename__ = "sale_idempotency"
    __table_args__ = (Index("uq_sale_idempotency_user_key", "user_id", "idempotency_key", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transactions.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    user: Mapped[User] = relationship()
    transaction: Mapped[Transaction | None] = relationship()
