"""Add operating dates without inferring historical status from sales.

Revision ID: 20261104_01
Revises: 20261027_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20261104_01"
down_revision = "20261027_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operating_days",
        sa.Column("business_date", sa.Date(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("closure_reason", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('Open', 'Closed', 'Unknown', 'PlannedClosed')", name="ck_operating_days_status"),
        sa.CheckConstraint(
            "(status IN ('Closed', 'PlannedClosed') AND "
            "NULLIF(BTRIM(closure_reason), '') IS NOT NULL AND LENGTH(closure_reason) <= 500) OR "
            "(status IN ('Open', 'Unknown') AND closure_reason IS NULL)",
            name="ck_operating_days_reason",
        ),
        sa.CheckConstraint("version > 0", name="ck_operating_days_version"),
    )


def downgrade() -> None:
    raise RuntimeError("operating_days downgrade is unsafe: recorded statuses and audit history must be preserved")
