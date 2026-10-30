"""Synthetic restore-check tests. No PostgreSQL connection or backup is opened."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "backup" / "verify_restore.py"
SPEC = importlib.util.spec_from_file_location("restore_verifier_under_test", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, *, actual="yabs_salon_restore_drill", schema="public", revision=verifier.REVISION,
                 tables=None, fail_check=None, attempt_states=None):
        self.actual = actual
        self.schema = schema
        self.revision = revision
        self.tables = tables if tables is not None else verifier.REQUIRED_TABLES
        self.fail_check = fail_check
        self.attempt_states = attempt_states if attempt_states is not None else [("Cancelled", 2), ("Committed", 3)]
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)
        if sql == "SELECT current_database()":
            return Result([(self.actual,)])
        if sql == "SELECT current_user":
            return Result([("restore_reader",)])
        if sql == "SELECT current_schema()":
            return Result([(self.schema,)])
        if "information_schema.tables" in sql:
            return Result([(name,) for name in self.tables])
        if "SELECT version_num FROM public.alembic_version" in sql:
            return Result([(self.revision,)] if self.revision else [])
        if "SELECT conname FROM pg_constraint" in sql:
            return Result([(name,) for name in verifier.REQUIRED_CONSTRAINTS])
        if "SELECT indexrelid::regclass::text" in sql:
            return Result([(name,) for name in verifier.REQUIRED_INDEXES])
        if "SELECT state,count(*)" in sql:
            return Result(self.attempt_states)
        for code, check in verifier.CHECKS:
            if sql == check:
                return Result([(1 if code == self.fail_check else 0,)])
        if sql.startswith("BEGIN ") or sql == "ROLLBACK":
            return Result([])
        raise AssertionError("Unexpected SQL")


@pytest.fixture
def target(monkeypatch):
    for key, value in {
        "HOST": "isolated-db", "PORT": "5432", "NAME": "yabs_salon_restore_drill",
        "USER": "restore_reader", "PASSWORD": "synthetic-secret-never-log",
    }.items():
        monkeypatch.setenv("RESTORE_DB_" + key, value)
    return verifier.target_from_environment(expected_db="yabs_salon_restore_drill",
                                            expected_host="isolated-db", expected_user="restore_reader")


@pytest.mark.parametrize("name", ["yabs_salon_dev", "yabs_salon_test", "salon_production", "", "yabs_salon_restore_"])
def test_rejects_non_isolated_database_before_connection(target, name):
    with pytest.raises(verifier.VerificationError, match="unsafe_target"):
        verifier.target_from_environment(expected_db=name, expected_host=target.host, expected_user=target.user)


def test_requires_matching_explicit_host_user_and_configured_name(target, monkeypatch):
    for overrides in (
        {"expected_host": "production-host"}, {"expected_user": "other"},
        {"expected_db": "yabs_salon_restore_other"},
    ):
        with pytest.raises(verifier.VerificationError):
            verifier.target_from_environment(expected_db=overrides.get("expected_db", target.database),
                expected_host=overrides.get("expected_host", target.host),
                expected_user=overrides.get("expected_user", target.user))
    monkeypatch.delenv("RESTORE_DB_PASSWORD")
    with pytest.raises(verifier.VerificationError, match="target_mismatch"):
        verifier.target_from_environment(expected_db=target.database,
                                         expected_host=target.host, expected_user=target.user)


@pytest.mark.parametrize("change,code", [
    ({"actual": "other"}, "connected_target_mismatch"),
    ({"schema": "other"}, "connected_target_mismatch"),
    ({"tables": {"alembic_version"}}, "schema_missing"),
    ({"revision": "20261020_01"}, "revision_mismatch"),
    ({"attempt_states": [("Unknown", 1)]}, "attempt_state_invalid"),
])
def test_rejects_wrong_identity_schema_or_state(target, change, code):
    connection = FakeConnection(**change)
    with pytest.raises(verifier.VerificationError, match=code):
        verifier.verify_restore(connection, target)
    assert connection.statements[-1] == "ROLLBACK"


@pytest.mark.parametrize("code", [
    "attempt_state_invalid", "attempt_key_duplicate", "open_attempt_duplicate",
    "direct_reference_duplicate", "paper_reference_duplicate",
    "transaction_paper_duplicate", "paper_reference_conflict",
    "claim_invalid", "claim_duplicate", "transaction_claim_missing",
    "committed_attempt_claim_missing", "cancel_audit_missing",
    "manual_audit_missing", "void_audit_missing", "transaction_items_missing",
    "item_snapshot_invalid", "financial_reconciliation_failed",
])
def test_rejects_each_inconsistent_restored_state(target, code):
    connection = FakeConnection(fail_check=code)
    with pytest.raises(verifier.VerificationError, match=code):
        verifier.verify_restore(connection, target)
    assert connection.statements[-1] == "ROLLBACK"


def test_passes_consistent_snapshot_and_executes_only_read_only_sql(target):
    connection = FakeConnection()
    assert verifier.verify_restore(connection, target) == {"Reserved": 0, "Committed": 3, "Cancelled": 2}
    assert connection.statements[0] == "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert connection.statements[-1] == "ROLLBACK"
    assert all(statement.startswith("SELECT ") for statement in connection.statements[1:-1])


def test_cli_enforces_read_only_connection_and_hides_database_error(target, monkeypatch, capsys):
    seen = {}

    def connect(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("synthetic-secret-never-log")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    assert verifier.main(["--expected-db", target.database, "--expected-host", target.host,
                          "--expected-user", target.user]) == 1
    assert seen["autocommit"] is True
    assert "default_transaction_read_only=on" in seen["options"]
    assert seen["connect_timeout"] == 5
    assert "synthetic-secret-never-log" not in capsys.readouterr().err
