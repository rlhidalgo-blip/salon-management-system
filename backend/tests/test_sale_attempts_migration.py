"""Phase A schema checks; the optional PostgreSQL test always rolls back."""

import os
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import get_database_url
from app.db.model_registry import get_model_metadata


ROOT = Path(__file__).resolve().parents[1]
REVISION = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_revision("20261027_01").module


def test_additive_migration_matches_model(monkeypatch):
    metadata = sa.MetaData()
    indexes = []

    def create_table(name, *columns):
        sa.Table(name, metadata, *columns)

    monkeypatch.setattr(REVISION.op, "create_table", create_table)
    monkeypatch.setattr(REVISION.op, "create_index", lambda *args, **kwargs: indexes.append((args, kwargs)))
    REVISION.upgrade()
    assert set(metadata.tables) == {"sale_attempts"}
    actual = metadata.tables["sale_attempts"]
    expected = get_model_metadata().tables["sale_attempts"]
    assert [(c.name, str(c.type), c.nullable, bool(c.computed)) for c in actual.columns] == [
        (c.name, str(c.type), c.nullable, bool(c.computed)) for c in expected.columns
    ]
    assert {(c.name, str(c.sqltext)) for c in actual.constraints if isinstance(c, sa.CheckConstraint)} == {
        (c.name, str(c.sqltext)) for c in expected.constraints if isinstance(c, sa.CheckConstraint)
    }
    assert {(c.name, tuple(c.columns.keys())) for c in actual.constraints if isinstance(c, sa.UniqueConstraint)} == {
        (c.name, tuple(c.columns.keys())) for c in expected.constraints if isinstance(c, sa.UniqueConstraint)
    }
    assert {(fk.parent.name, fk.target_fullname, fk.ondelete) for fk in actual.foreign_keys} == {
        (fk.parent.name, fk.target_fullname, fk.ondelete) for fk in expected.foreign_keys
    }
    assert {args[0] for args, _ in indexes} == {index.name for index in expected.indexes}


def _preflight(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured test database")
    if (connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"):
        raise RuntimeError("Unsafe connected test database")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if address is None or not ip_address(str(address)).is_loopback:
        raise RuntimeError("Database host is not loopback")
    revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
    exists = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
    if (connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1
            or (revision, exists) not in (("20261020_01", False), ("20261027_01", True))):
        raise RuntimeError("Unexpected Alembic revision or sale_attempts state")
    return exists


def test_additive_migration_on_isolated_postgres_rollback_only():
    if os.getenv("RUN_SALE_ATTEMPT_SCHEMA_TESTS") != "1":
        pytest.skip("Set RUN_SALE_ATTEMPT_SCHEMA_TESTS=1 for guarded yabs_salon_test schema check")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured test database; no connection attempted")
    engine = sa.create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            migrated = _preflight(connection, url)
            legacy_before = (
                connection.scalar(text("SELECT count(*) FROM transactions")),
                connection.scalar(text("SELECT count(*) FROM sale_idempotency")),
            )
            transaction = connection.begin_nested()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '3s'"))
                connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                if not migrated:
                    with Operations.context(MigrationContext.configure(connection)):
                        REVISION.upgrade()
                assert connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
                user_id = connection.scalar(text(
                    "INSERT INTO users (username, password_hash, role) "
                    "VALUES (:name, 'synthetic-unused', 'Cashier') RETURNING id"
                ), {"name": "synthetic-attempt-" + str(uuid4())})
                def insert(source="Direct", state="Reserved", reference=None, **extra):
                    values = {
                        "user_id": user_id, "key": str(uuid4()), "source": source, "state": state,
                        "hash": "a" * 64, "reference": reference,
                        "transaction_id": None, "committed_at": None, "cancelled_at": None,
                        "actor": None, "reason": None,
                    } | extra
                    return connection.execute(text(
                        "INSERT INTO sale_attempts (user_id, idempotency_key, source, state, request_hash, "
                        "manual_reference, transaction_id, committed_at, cancelled_at, cancelled_by_user_id, cancellation_reason) "
                        "VALUES (:user_id, :key, :source, :state, :hash, :reference, :transaction_id, "
                        ":committed_at, :cancelled_at, :actor, :reason) RETURNING id, direct_reference"
                    ), values).one()

                def rejected(sqlstate, **kwargs):
                    savepoint = connection.begin_nested()
                    try:
                        with pytest.raises(sa.exc.DBAPIError) as error:
                            insert(**kwargs)
                        assert error.value.orig.sqlstate == sqlstate
                    finally:
                        savepoint.rollback()

                first_id, direct_ref = insert()
                assert direct_ref == f"DS-{first_id:012d}"
                rejected("23505")  # second Reserved attempt for same user
                connection.execute(text(
                    "UPDATE sale_attempts SET state='Cancelled', cancelled_at=now(), "
                    "cancelled_by_user_id=:user_id, cancellation_reason='Evidence checked' WHERE id=:id"
                ), {"user_id": user_id, "id": first_id})
                rejected("23505", key=connection.scalar(text("SELECT idempotency_key::text FROM sale_attempts WHERE id=:id"), {"id": first_id}))
                paper = "PAPER-20261027-001"
                manual_id, _ = insert(source="Manual", reference=paper)
                connection.execute(text(
                    "UPDATE sale_attempts SET state='Cancelled', cancelled_at=now(), "
                    "cancelled_by_user_id=:user_id, cancellation_reason='Evidence checked' WHERE id=:id"
                ), {"user_id": user_id, "id": manual_id})
                rejected("23505", source="Manual", reference=paper)
                rejected("23514", source="Manual", reference="paper-20261027-002")
                rejected("23514", state="Cancelled", reason=" ")
                rejected("23514", state="Cancelled", cancelled_at=connection.scalar(text("SELECT now()")),
                         actor=user_id, reason="x" * 501)
                rejected("23514", state="Committed")
                rejected("23514", source="Direct", reference=paper)
                rejected("23514", hash="not-a-digest")
                sale_id = connection.scalar(text(
                    "INSERT INTO transactions (business_date, recorded_by_user_id, entry_source, payment_method) "
                    "VALUES (DATE '2026-10-27', :user_id, 'Direct', 'Cash') RETURNING id"
                ), {"user_id": user_id})
                committed_id, _ = insert()
                connection.execute(text(
                    "UPDATE sale_attempts SET state='Committed', transaction_id=:sale_id, "
                    "committed_at=now() WHERE id=:id"
                ), {"sale_id": sale_id, "id": committed_id})
                assert connection.scalar(text("SELECT count(*) FROM sale_attempts")) == 3
            finally:
                transaction.rollback()
                connection.rollback()
        with engine.connect() as verifier:
            _preflight(verifier, url)
            assert (
                verifier.scalar(text("SELECT count(*) FROM transactions")),
                verifier.scalar(text("SELECT count(*) FROM sale_idempotency")),
            ) == legacy_before
    finally:
        engine.dispose()
