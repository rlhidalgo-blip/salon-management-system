"""Offline migration checks; never connect to a database."""

from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql

from app.modules.operating_days.models import OperatingDay


ROOT = Path(__file__).resolve().parents[1]
REVISION = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_revision("20261104_01").module


def test_additive_migration_matches_calendar_model(monkeypatch):
    tables = []
    monkeypatch.setattr(REVISION.op, "create_table", lambda name, *columns: tables.append((name, columns)))
    REVISION.upgrade()
    assert len(tables) == 1 and tables[0][0] == "operating_days"
    created = {column.name: column for column in tables[0][1] if hasattr(column, "name") and hasattr(column, "type")}
    model = OperatingDay.__table__
    assert set(created) == set(model.columns.keys())
    for name, column in created.items():
        expected = model.c[name]
        assert column.type.compile(dialect=postgresql.dialect()) == expected.type.compile(dialect=postgresql.dialect())
        assert column.nullable == expected.nullable
        assert column.primary_key == expected.primary_key
        assert {key.target_fullname for key in column.foreign_keys} == {key.target_fullname for key in expected.foreign_keys}
    assert {(item.name, str(item.sqltext)) for item in tables[0][1] if hasattr(item, "sqltext")} == {
        (item.name, str(item.sqltext)) for item in model.constraints if hasattr(item, "sqltext")
    }


def test_offline_upgrade_only_creates_calendar_table_and_downgrade_refuses():
    output = StringIO()
    context = MigrationContext.configure(dialect=postgresql.dialect(), opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        REVISION.upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE ") == 1
    assert "operating_days" in sql
    assert "DROP TABLE" not in sql
    try:
        REVISION.downgrade()
    except RuntimeError as error:
        assert "unsafe" in str(error)
    else:
        raise AssertionError("downgrade must refuse data deletion")
