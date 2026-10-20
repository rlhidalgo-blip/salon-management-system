from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.base import Base
from app.db.model_registry import get_model_metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_paths_and_single_initial_revision() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert Path(script.dir) == BACKEND_ROOT / "migrations"
    assert Path(script.versions) == BACKEND_ROOT / "migrations" / "versions"
    assert script.get_heads() == ["20261020_01"]
    revision = script.get_revision("20261020_01")
    assert revision.down_revision is None
    assert config.get_main_option("sqlalchemy.url") is None


def test_model_registry_uses_shared_metadata_with_all_approved_models() -> None:
    assert get_model_metadata() is Base.metadata
    assert set(Base.metadata.tables) == {
        "users",
        "staff",
        "commission_rules",
        "services",
        "products",
        "transactions",
        "transaction_items",
        "auth_sessions",
        "audit_events",
        "sale_idempotency",
    }
