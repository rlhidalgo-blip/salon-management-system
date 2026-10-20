from sqlalchemy import BigInteger, CHAR, CheckConstraint, Date, Integer, Numeric, Text, TIMESTAMP, inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID, dialect
from sqlalchemy.schema import CreateTable

from app.db.model_registry import get_model_metadata
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


EXPECTED_COLUMNS = {
    "transactions": {
        "id", "date_time", "business_date", "created_at", "recorded_by_user_id", "entry_source",
        "manual_reference", "payment_method", "gcash_reference", "status", "void_reason",
        "voided_by_user_id", "voided_at",
    },
    "transaction_items": {
        "id", "transaction_id", "service_id", "product_id", "staff_id", "item_name_snapshot",
        "selling_price", "commission_type_snapshot", "commission_value_snapshot", "staff_commission",
        "business_share",
    },
    "auth_sessions": {
        "id", "user_id", "token_hash", "created_at", "last_activity_at", "expires_at", "revoked_at",
    },
    "audit_events": {
        "id", "actor_user_id", "event_type", "resource_type", "resource_id", "outcome", "occurred_at", "metadata",
    },
    "sale_idempotency": {
        "id", "user_id", "idempotency_key", "request_hash", "transaction_id", "created_at",
    },
}


def test_columns_types_and_nullability_match_v11() -> None:
    metadata = get_model_metadata()
    required_columns = {
        "transactions": {
            "id", "date_time", "business_date", "created_at", "recorded_by_user_id", "entry_source",
            "payment_method", "status",
        },
        "transaction_items": {
            "id", "transaction_id", "item_name_snapshot", "selling_price", "staff_commission", "business_share",
        },
        "auth_sessions": {"id", "user_id", "token_hash", "created_at", "last_activity_at", "expires_at"},
        "audit_events": {"id", "event_type", "outcome", "occurred_at"},
        "sale_idempotency": {"id", "user_id", "idempotency_key", "request_hash", "created_at"},
    }

    for table_name, expected in EXPECTED_COLUMNS.items():
        table = metadata.tables[table_name]
        assert set(table.columns.keys()) == expected
        assert {column.name for column in table.columns if not column.nullable} == required_columns[table_name]
        assert table.c.id.primary_key

    for table_name in ("transactions", "transaction_items"):
        assert isinstance(metadata.tables[table_name].c.id.type, Integer)
    for table_name in ("audit_events", "sale_idempotency"):
        assert isinstance(metadata.tables[table_name].c.id.type, BigInteger)
        assert metadata.tables[table_name].c.id.identity.always is False
    assert isinstance(metadata.tables["auth_sessions"].c.id.type, UUID)
    assert isinstance(metadata.tables["transactions"].c.business_date.type, Date)
    assert isinstance(metadata.tables["audit_events"].c.metadata.type, JSONB)

    for table_name, columns in {
        "transactions": ("date_time", "created_at", "voided_at"),
        "auth_sessions": ("created_at", "last_activity_at", "expires_at", "revoked_at"),
        "audit_events": ("occurred_at",),
        "sale_idempotency": ("created_at",),
    }.items():
        for name in columns:
            column_type = metadata.tables[table_name].c[name].type
            assert isinstance(column_type, TIMESTAMP) and column_type.timezone

    for name in ("selling_price", "commission_value_snapshot", "staff_commission", "business_share"):
        column_type = metadata.tables["transaction_items"].c[name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale, column_type.asdecimal) == (12, 2, True)
    assert isinstance(metadata.tables["auth_sessions"].c.token_hash.type, CHAR)
    assert metadata.tables["auth_sessions"].c.token_hash.type.length == 64
    assert isinstance(metadata.tables["sale_idempotency"].c.request_hash.type, CHAR)
    assert metadata.tables["sale_idempotency"].c.request_hash.type.length == 64
    assert isinstance(metadata.tables["transaction_items"].c.item_name_snapshot.type, Text)
    assert "quantity" not in metadata.tables["transaction_items"].c


def test_foreign_keys_and_distinct_user_relationships() -> None:
    metadata = get_model_metadata()
    expected_fks = {
        "transactions": {
            "recorded_by_user_id": "users.id", "voided_by_user_id": "users.id",
        },
        "transaction_items": {
            "transaction_id": "transactions.id", "service_id": "services.id",
            "product_id": "products.id", "staff_id": "staff.id",
        },
        "auth_sessions": {"user_id": "users.id"},
        "audit_events": {"actor_user_id": "users.id"},
        "sale_idempotency": {"user_id": "users.id", "transaction_id": "transactions.id"},
    }
    for table_name, fields in expected_fks.items():
        table = metadata.tables[table_name]
        assert {column.name for column in table.columns if column.foreign_keys} == set(fields)
        for name, target in fields.items():
            foreign_key = next(iter(table.c[name].foreign_keys))
            assert foreign_key.target_fullname == target
            assert foreign_key.ondelete == "RESTRICT"

    recorded_by = inspect(Transaction).relationships["recorded_by"]
    voided_by = inspect(Transaction).relationships["voided_by"]
    assert recorded_by.mapper.class_ is User
    assert voided_by.mapper.class_ is User
    assert recorded_by.local_columns == {Transaction.__table__.c.recorded_by_user_id}
    assert voided_by.local_columns == {Transaction.__table__.c.voided_by_user_id}
    assert inspect(Transaction).relationships["items"].mapper.class_ is TransactionItem
    assert inspect(TransactionItem).relationships["transaction"].mapper.class_ is Transaction
    assert inspect(AuthSession).relationships["user"].mapper.class_ is User
    assert inspect(AuditEvent).relationships["actor"].mapper.class_ is User
    assert inspect(SaleIdempotency).relationships["transaction"].mapper.class_ is Transaction


def test_approved_indexes_and_uniqueness() -> None:
    metadata = get_model_metadata()
    transaction_indexes = {index.name: index for index in metadata.tables["transactions"].indexes}
    assert set(transaction_indexes) == {
        "ix_transactions_date_time", "ix_transactions_business_date",
        "ix_transactions_recorded_by_user_id", "uq_transactions_manual_reference",
    }
    manual_reference = transaction_indexes["uq_transactions_manual_reference"]
    assert manual_reference.unique
    assert set(manual_reference.columns.keys()) == {"manual_reference"}
    assert str(manual_reference.dialect_options["postgresql"]["where"]) == "manual_reference IS NOT NULL"

    session_indexes = {index.name: index for index in metadata.tables["auth_sessions"].indexes}
    assert set(session_indexes) == {"ix_auth_sessions_user_id", "uq_auth_sessions_token_hash"}
    assert not session_indexes["ix_auth_sessions_user_id"].unique
    assert session_indexes["uq_auth_sessions_token_hash"].unique
    assert {index.name for index in metadata.tables["audit_events"].indexes} == {"ix_audit_events_occurred_at"}
    idempotency_index = next(iter(metadata.tables["sale_idempotency"].indexes))
    assert idempotency_index.unique
    assert set(idempotency_index.columns.keys()) == {"user_id", "idempotency_key"}


def test_payment_void_manual_and_financial_checks_are_declared() -> None:
    metadata = get_model_metadata()
    transaction_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in metadata.tables["transactions"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    item_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in metadata.tables["transaction_items"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert set(transaction_checks) == {
        "ck_transactions_payment_method", "ck_transactions_gcash_reference", "ck_transactions_status",
        "ck_transactions_void_metadata", "ck_transactions_entry_source", "ck_transactions_manual_reference",
    }
    assert "gcash_reference IS NULL" in transaction_checks["ck_transactions_gcash_reference"]
    assert "voided_by_user_id IS NOT NULL" in transaction_checks["ck_transactions_void_metadata"]
    assert "entry_source = 'Manual'" in transaction_checks["ck_transactions_manual_reference"]
    assert set(item_checks) == {
        "ck_transaction_items_one_item_type", "ck_transaction_items_service_staff",
        "ck_transaction_items_selling_price", "ck_transaction_items_staff_commission",
        "ck_transaction_items_business_share", "ck_transaction_items_commission_limit",
        "ck_transaction_items_financial_total", "ck_transaction_items_commission_snapshot",
        "ck_transaction_items_commission_assignment",
    }
    assert item_checks["ck_transaction_items_financial_total"] == "staff_commission + business_share = selling_price"
    assert "commission_value_snapshot IS NOT NULL" in item_checks["ck_transaction_items_commission_snapshot"]
    assert item_checks["ck_transaction_items_commission_assignment"].count("commission_type_snapshot IS NOT NULL") == 2
    assert "staff_commission = 0" in item_checks["ck_transaction_items_commission_assignment"]
    assert any(
        isinstance(constraint, CheckConstraint) and str(constraint.sqltext) == "outcome IN ('Success', 'Failure')"
        for constraint in metadata.tables["audit_events"].constraints
    )


def test_postgresql_ddl_compiles_with_audit_metadata_column() -> None:
    metadata = get_model_metadata()
    for table_name in EXPECTED_COLUMNS:
        ddl = str(CreateTable(metadata.tables[table_name]).compile(dialect=dialect()))
        assert "CREATE TABLE" in ddl
    assert "metadata JSONB" in str(CreateTable(metadata.tables["audit_events"]).compile(dialect=dialect()))
    assert AuditEvent.__table__.c.metadata.name == "metadata"
    assert AuditEvent.event_metadata.property.columns[0].name == "metadata"
