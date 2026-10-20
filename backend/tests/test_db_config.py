from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.core import config
from app.db import session


def test_database_url_uses_environment_without_exposing_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name, value in {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "yabs_salon_dev",
        "DB_USER": "yabs_app",
        "DB_PASSWORD": "local:test@password",
    }.items():
        monkeypatch.setenv(name, value)

    url = config.get_database_url()

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "yabs_app"
    assert url.password == "local:test@password"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "yabs_salon_dev"
    assert "local:test@password" not in str(url)


def test_database_url_requires_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name, value in {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "yabs_salon_dev",
        "DB_USER": "yabs_app",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="DB_PASSWORD"):
        config.get_database_url()


def test_connectivity_check_runs_select_one_without_live_database(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1
    monkeypatch.setattr(session, "get_engine", lambda: engine)

    assert session.check_database_connection() is True
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"


def test_connectivity_check_handles_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("SELECT 1", {}, Exception("unavailable"))
    monkeypatch.setattr(session, "get_engine", lambda: engine)

    assert session.check_database_connection() is False
