"""Initial approved Database Design v1.1 schema.

Revision ID: 20261020_01
Revises:
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261020_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("role IN ('Owner', 'Cashier')", name="ck_users_role"),
    )

    op.create_table(
        "staff",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("role IN ('Barber', 'Stylist')", name="ck_staff_role"),
    )

    op.create_table(
        "commission_rules",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("type IN ('Percentage', 'Fixed')", name="ck_commission_rules_type"),
        sa.CheckConstraint(
            "value > 0 AND (type <> 'Percentage' OR value <= 100)",
            name="ck_commission_rules_value",
        ),
    )

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("allows_variable_price", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("commission_rule_id", sa.Integer(), sa.ForeignKey("commission_rules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("current_price > 0", name="ck_services_current_price"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_rule_id", sa.Integer(), sa.ForeignKey("commission_rules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("current_price > 0", name="ck_products_current_price"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("date_time", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_source", sa.Text(), nullable=False),
        sa.Column("manual_reference", sa.Text(), nullable=True),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("gcash_reference", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'Completed'"), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("payment_method IN ('Cash', 'GCash')", name="ck_transactions_payment_method"),
        sa.CheckConstraint(
            "(payment_method = 'Cash' AND gcash_reference IS NULL) OR "
            "(payment_method = 'GCash' AND NULLIF(BTRIM(gcash_reference), '') IS NOT NULL)",
            name="ck_transactions_gcash_reference",
        ),
        sa.CheckConstraint("status IN ('Completed', 'Voided')", name="ck_transactions_status"),
        sa.CheckConstraint(
            "(status = 'Completed' AND void_reason IS NULL AND voided_by_user_id IS NULL AND voided_at IS NULL) OR "
            "(status = 'Voided' AND NULLIF(BTRIM(void_reason), '') IS NOT NULL "
            "AND voided_by_user_id IS NOT NULL AND voided_at IS NOT NULL)",
            name="ck_transactions_void_metadata",
        ),
        sa.CheckConstraint("entry_source IN ('Direct', 'Manual')", name="ck_transactions_entry_source"),
        sa.CheckConstraint(
            "(entry_source = 'Direct' AND manual_reference IS NULL) OR "
            "(entry_source = 'Manual' AND NULLIF(BTRIM(manual_reference), '') IS NOT NULL)",
            name="ck_transactions_manual_reference",
        ),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=True),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("outcome IN ('Success', 'Failure')", name="ck_audit_events_outcome"),
    )

    op.create_table(
        "transaction_items",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("item_name_snapshot", sa.Text(), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_type_snapshot", sa.Text(), nullable=True),
        sa.Column("commission_value_snapshot", sa.Numeric(12, 2), nullable=True),
        sa.Column("staff_commission", sa.Numeric(12, 2), nullable=False),
        sa.Column("business_share", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint(
            "(service_id IS NOT NULL AND product_id IS NULL) OR "
            "(service_id IS NULL AND product_id IS NOT NULL)",
            name="ck_transaction_items_one_item_type",
        ),
        sa.CheckConstraint("service_id IS NULL OR staff_id IS NOT NULL", name="ck_transaction_items_service_staff"),
        sa.CheckConstraint("selling_price > 0", name="ck_transaction_items_selling_price"),
        sa.CheckConstraint("staff_commission >= 0", name="ck_transaction_items_staff_commission"),
        sa.CheckConstraint("business_share >= 0", name="ck_transaction_items_business_share"),
        sa.CheckConstraint("staff_commission <= selling_price", name="ck_transaction_items_commission_limit"),
        sa.CheckConstraint(
            "staff_commission + business_share = selling_price",
            name="ck_transaction_items_financial_total",
        ),
        sa.CheckConstraint(
            "(commission_type_snapshot IS NULL AND commission_value_snapshot IS NULL) OR "
            "(commission_type_snapshot IN ('Percentage', 'Fixed') "
            "AND commission_value_snapshot IS NOT NULL AND commission_value_snapshot > 0 "
            "AND (commission_type_snapshot <> 'Percentage' OR commission_value_snapshot <= 100))",
            name="ck_transaction_items_commission_snapshot",
        ),
        sa.CheckConstraint(
            "(service_id IS NOT NULL AND commission_type_snapshot IS NOT NULL "
            "AND commission_type_snapshot = 'Percentage') OR "
            "(product_id IS NOT NULL AND staff_id IS NOT NULL AND commission_type_snapshot IS NOT NULL "
            "AND commission_type_snapshot = 'Fixed') OR "
            "(product_id IS NOT NULL AND staff_id IS NULL AND commission_type_snapshot IS NULL "
            "AND commission_value_snapshot IS NULL AND staff_commission = 0)",
            name="ck_transaction_items_commission_assignment",
        ),
    )

    op.create_table(
        "sale_idempotency",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_index("ix_transactions_date_time", "transactions", ["date_time"])
    op.create_index("ix_transactions_business_date", "transactions", ["business_date"])
    op.create_index("ix_transactions_recorded_by_user_id", "transactions", ["recorded_by_user_id"])
    op.create_index(
        "uq_transactions_manual_reference",
        "transactions",
        ["manual_reference"],
        unique=True,
        postgresql_where=sa.text("manual_reference IS NOT NULL"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("uq_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("uq_sale_idempotency_user_key", "sale_idempotency", ["user_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    # Destructive if executed: drops all ten tables and their data.
    op.drop_index("uq_sale_idempotency_user_key", table_name="sale_idempotency")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_index("uq_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("uq_transactions_manual_reference", table_name="transactions")
    op.drop_index("ix_transactions_recorded_by_user_id", table_name="transactions")
    op.drop_index("ix_transactions_business_date", table_name="transactions")
    op.drop_index("ix_transactions_date_time", table_name="transactions")

    op.drop_table("sale_idempotency")
    op.drop_table("transaction_items")
    op.drop_table("audit_events")
    op.drop_table("auth_sessions")
    op.drop_table("transactions")
    op.drop_table("products")
    op.drop_table("services")
    op.drop_table("commission_rules")
    op.drop_table("staff")
    op.drop_table("users")
