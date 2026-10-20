from sqlalchemy import Boolean, CheckConstraint, Identity, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (CheckConstraint("role IN ('Barber', 'Stylist')", name="ck_staff_role"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
