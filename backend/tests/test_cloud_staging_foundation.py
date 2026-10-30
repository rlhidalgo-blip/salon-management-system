"""Cloud foundation checks use temporary files and mocked DB engines only."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core import config, startup, static
from app.db import session
from app.main import app


def test_react_assets_spa_and_api_404_are_separate(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>synthetic app</html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("// synthetic asset", encoding="utf-8")
    monkeypatch.setattr(static, "FRONTEND_DIST", tmp_path)
    client = TestClient(app)
    assert "synthetic app" in client.get("/").text
    assert "synthetic app" in client.get("/history").text
    assert client.get("/assets/app.js").text == "// synthetic asset"
    for path in ("/api/v1/not-a-route", "/api/v1/services/not-a-route", "/assets/missing.js"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "http_error"
    assert client.post("/api/v1/not-a-route").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}


@pytest.fixture
def database_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("DB_HOST", "ep-synthetic.neon.tech")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "yabs_salon_staging")
    monkeypatch.setenv("DB_USER", "synthetic_user")
    monkeypatch.setenv("DB_PASSWORD", "synthetic_password")
    monkeypatch.delenv("DB_SSLMODE", raising=False)


def test_neon_requires_verified_tls(database_env, monkeypatch):
    with pytest.raises(ValueError, match="verify-full"):
        config.get_database_url()
    monkeypatch.setenv("DB_SSLMODE", "require")
    with pytest.raises(ValueError, match="verify-full"):
        config.get_database_url()
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    url = config.get_database_url()
    assert url.database == "yabs_salon_staging"
    assert url.query["sslmode"] == "verify-full"


def test_local_database_keeps_default_connection_mode(database_env, monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    assert not config.get_database_url().query
    monkeypatch.setenv("DB_SSLMODE", "disable")
    with pytest.raises(ValueError, match="DB_SSLMODE"):
        config.get_database_url()


def test_staging_pool_is_bounded(database_env, monkeypatch):
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    engine = MagicMock()
    factory = MagicMock(return_value=engine)
    monkeypatch.setattr(session, "create_engine", factory)
    session.get_engine.cache_clear()
    try:
        assert session.get_engine() is engine
        kwargs = factory.call_args.kwargs
        assert kwargs == {"pool_pre_ping": True, "pool_size": 2, "max_overflow": 0}
        assert factory.call_args.args[0].query["sslmode"] == "verify-full"
    finally:
        session.get_engine.cache_clear()


@pytest.mark.parametrize("setting,value", [("DB_POOL_SIZE", "0"), ("DB_MAX_OVERFLOW", "-1"), ("DB_POOL_SIZE", "many")])
def test_invalid_pool_rejected_before_connection(database_env, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    factory = MagicMock()
    monkeypatch.setattr(session, "create_engine", factory)
    session.get_engine.cache_clear()
    try:
        with pytest.raises(ValueError, match="pool"):
            session.get_engine()
        factory.assert_not_called()
    finally:
        session.get_engine.cache_clear()


def test_production_preflight_rejects_unverified_neon_before_connection(database_env, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_EXPECTED_NAME", "yabs_salon_staging")
    monkeypatch.setenv("AUTH_COOKIE_MODE", "production")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "https://synthetic.onrender.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-secret-that-is-at-least-32-bytes")
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    factory = MagicMock()
    monkeypatch.setattr(startup, "get_engine", factory)
    with pytest.raises(ValueError, match="verify-full"):
        startup.validate_startup_configuration()
    factory.assert_not_called()
