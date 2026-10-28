"""Add durable sale-attempt fences without changing existing sales.

Revision ID: 20261027_01
Revises: 20261020_01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261027_01"
down_revision = "20261020_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sale_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'Reserved'")),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("direct_reference", sa.Text(), sa.Computed(
            "CASE WHEN source = 'Direct' THEN 'DS-' || "
            "LPAD(id::text, GREATEST(12, LENGTH(id::text)), '0') ELSE NULL END", persisted=True,
        )),
        sa.Column("manual_reference", sa.Text()),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("committed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("cancellation_reason", sa.Text()),
        sa.CheckConstraint("source IN ('Direct', 'Manual')", name="ck_sale_attempts_source"),
        sa.CheckConstraint("state IN ('Reserved', 'Committed', 'Cancelled')", name="ck_sale_attempts_state"),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_sale_attempts_request_hash"),
        sa.CheckConstraint(
            "(source = 'Direct' AND manual_reference IS NULL) OR "
            "(source = 'Manual' AND manual_reference ~ '^PAPER-[0-9]{8}-[0-9]{3}$')",
            name="ck_sale_attempts_reference_source",
        ),
        sa.CheckConstraint(
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
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_sale_attempts_user_key"),
        sa.UniqueConstraint("direct_reference", name="uq_sale_attempts_direct_reference"),
        sa.UniqueConstraint("manual_reference", name="uq_sale_attempts_manual_reference"),
        sa.UniqueConstraint("transaction_id", name="uq_sale_attempts_transaction_id"),
    )
    op.create_index(
        "uq_sale_attempts_one_reserved_user", "sale_attempts", ["user_id"], unique=True,
        postgresql_where=sa.text("state = 'Reserved'"),
    )
    op.create_index("ix_sale_attempts_user_created", "sale_attempts", ["user_id", "created_at", "id"])


def downgrade() -> None:
    # Deliberately refuse deletion: attempts (especially Cancelled) are permanent fences.
    raise RuntimeError("sale_attempts downgrade is unsafe: preserved sale keys and references must not be deleted")
