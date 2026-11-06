from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperatingDay(Base):
    __tablename__ = "operating_days"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Open', 'Closed', 'Unknown', 'PlannedClosed')",
            name="ck_operating_days_status",
        ),
        CheckConstraint(
            "(status IN ('Closed', 'PlannedClosed') AND "
            "NULLIF(BTRIM(closure_reason), '') IS NOT NULL AND LENGTH(closure_reason) <= 500) OR "
            "(status IN ('Open', 'Unknown') AND closure_reason IS NULL)",
            name="ck_operating_days_reason",
        ),
        CheckConstraint("version > 0", name="ck_operating_days_version"),
    )

    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    closure_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False)
