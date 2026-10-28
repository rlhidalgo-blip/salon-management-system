from io import StringIO
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.db.model_registry import get_model_metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INITIAL_REVISION = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_revision(
    "20261020_01"
).module


def _column_signature(column: sa.Column) -> tuple:
    return (
        column.name,
        str(column.type.compile(dialect=postgresql.dialect())),
        column.nullable,
        column.primary_key,
        None if column.identity is None else column.identity.always,
        None if column.server_default is None or column.identity is not None else str(column.server_default.arg),
    )


def _constraint_signature(table: sa.Table) -> tuple:
    checks = {
        (constraint.name, str(constraint.sqltext))
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    unique = {
        (constraint.name, tuple(constraint.columns.keys()))
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    foreign_keys = {
        (column.name, foreign_key.target_fullname, foreign_key.ondelete)
        for column in table.columns
        for foreign_key in column.foreign_keys
    }
    return checks, unique, foreign_keys, tuple(table.primary_key.columns.keys())


def _index_signature(name: str, columns: list[str], unique: bool, where: object) -> tuple:
    return name, tuple(columns), unique, None if where is None else str(where)


def test_initial_upgrade_matches_registered_metadata(monkeypatch) -> None:
    migration_metadata = sa.MetaData()
    create_order: list[str] = []
    created_indexes: dict[str, set[tuple]] = {}

    def capture_table(name: str, *elements: object, **kwargs: object) -> None:
        assert not kwargs
        sa.Table(name, migration_metadata, *elements)
        create_order.append(name)

    def capture_index(name: str, table_name: str, columns: list[str], **kwargs: object) -> None:
        created_indexes.setdefault(table_name, set()).add(
            _index_signature(
                name,
                columns,
                bool(kwargs.get("unique", False)),
                kwargs.get("postgresql_where"),
            )
        )

    monkeypatch.setattr(INITIAL_REVISION.op, "create_table", capture_table)
    monkeypatch.setattr(INITIAL_REVISION.op, "create_index", capture_index)
    INITIAL_REVISION.upgrade()

    expected_metadata = get_model_metadata()
    assert set(migration_metadata.tables) == set(expected_metadata.tables) - {"sale_attempts"}
    assert len(create_order) == 10
    for table_name in create_order:
        table = migration_metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.name in create_order[: create_order.index(table_name)]

        expected_table = expected_metadata.tables[table_name]
        assert tuple(map(_column_signature, table.columns)) == tuple(map(_column_signature, expected_table.columns))
        assert _constraint_signature(table) == _constraint_signature(expected_table)

        expected_indexes = {
            _index_signature(
                index.name,
                list(index.columns.keys()),
                index.unique,
                index.dialect_options["postgresql"].get("where"),
            )
            for index in expected_table.indexes
        }
        assert created_indexes.get(table_name, set()) == expected_indexes


def _render_offline(function) -> str:
    output = StringIO()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(migration_context):
        function()
    return output.getvalue()


def test_offline_upgrade_contains_only_creation_statements() -> None:
    sql = _render_offline(INITIAL_REVISION.upgrade)

    assert sql.count("CREATE TABLE ") == 10
    assert sql.count("CREATE INDEX ") + sql.count("CREATE UNIQUE INDEX ") == 8
    assert "CREATE UNIQUE INDEX uq_transactions_manual_reference" in sql
    assert "WHERE manual_reference IS NOT NULL" in sql
    assert "metadata JSONB" in sql
    assert "DROP TABLE" not in sql
    assert "DROP INDEX" not in sql


def test_offline_downgrade_reverses_dependencies() -> None:
    sql = _render_offline(INITIAL_REVISION.downgrade)
    drop_order = [line.removeprefix("DROP TABLE ").removesuffix(";") for line in sql.splitlines() if line.startswith("DROP TABLE ")]

    assert drop_order == [
        "sale_idempotency", "transaction_items", "audit_events", "auth_sessions", "transactions",
        "products", "services", "commission_rules", "staff", "users",
    ]
    assert sql.count("DROP INDEX ") == 8
    assert "CREATE TABLE" not in sql
    assert "CREATE INDEX" not in sql
