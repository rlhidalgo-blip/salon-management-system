"""Deployment preflight tests never open a PostgreSQL connection."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core import config, startup
from app.main import app
from app.modules.transactions.attempt_feature import attempt_protocol_enabled


@pytest.fixture(autouse=True)
def isolated_switch(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_MODE", "production")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "https://salon.example")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-only-secret-with-more-than-32-bytes")
    monkeypatch.setenv("DB_HOST", "private-db")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "salon_production")
    monkeypatch.setenv("DB_EXPECTED_NAME", "salon_production")
    monkeypatch.setenv("DB_USER", "synthetic_app")
    monkeypatch.setenv("DB_PASSWORD", "synthetic-only-password")
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    attempt_protocol_enabled.cache_clear()
    yield
    attempt_protocol_enabled.cache_clear()


def fake_database(monkeypatch, *, actual="salon_production", schema="public", count=1,
                  revision="20261027_01", table="sale_attempts"):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = [actual, schema, count, revision, table]
    monkeypatch.setattr(startup, "get_engine", lambda: engine)
    return engine


def test_production_preflight_accepts_matching_identity_and_head(monkeypatch):
    engine = fake_database(monkeypatch)
    startup.validate_startup_configuration()
    engine.connect.assert_called_once()


@pytest.mark.parametrize("name,value", [
    ("AUTH_ALLOWED_ORIGIN", ""),
    ("AUTH_ALLOWED_ORIGIN", "http://salon.example"),
    ("AUTH_ALLOWED_ORIGIN", "https://salon.example/path"),
    ("AUTH_RATE_LIMIT_SECRET", "short"),
    ("AUTH_COOKIE_MODE", "localhost"),
])
def test_production_rejects_invalid_auth_before_connect(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    engine = fake_database(monkeypatch)
    with pytest.raises((RuntimeError, ValueError)):
        startup.validate_startup_configuration()
    engine.connect.assert_not_called()


@pytest.mark.parametrize("name,value", [
    ("DB_EXPECTED_NAME", ""),
    ("DB_EXPECTED_NAME", "yabs_salon_dev"),
    ("DB_EXPECTED_NAME", "other_database"),
])
def test_production_rejects_unapproved_configured_target(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="database|DB_EXPECTED_NAME"):
        startup.validate_startup_configuration()


@pytest.mark.parametrize("actual,schema,count,revision,table", [
    ("wrong_database", "public", 1, "20261027_01", "sale_attempts"),
    ("salon_production", "other", 1, "20261027_01", "sale_attempts"),
    ("salon_production", "public", 2, "20261027_01", "sale_attempts"),
    ("salon_production", "public", 1, "20261020_01", None),
    ("salon_production", "public", 1, "20261027_01", None),
])
def test_production_rejects_connected_target_or_schema(monkeypatch, actual, schema, count, revision, table):
    fake_database(monkeypatch, actual=actual, schema=schema, count=count, revision=revision, table=table)
    with pytest.raises(RuntimeError, match="database|migration"):
        startup.validate_startup_configuration()


def test_reserved_development_requires_compatible_schema(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "1")
    monkeypatch.setenv("DB_NAME", "yabs_salon_test")
    attempt_protocol_enabled.cache_clear()
    fake_database(monkeypatch, actual="yabs_salon_test", revision="20261020_01", table=None)
    with pytest.raises(RuntimeError, match="migration"):
        startup.validate_startup_configuration()


def test_invalid_switch_fails_before_database_connect(monkeypatch):
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "maybe")
    attempt_protocol_enabled.cache_clear()
    engine = fake_database(monkeypatch)
    with pytest.raises(RuntimeError, match="SALE_ATTEMPT_PROTOCOL_ENABLED"):
        startup.validate_startup_configuration()
    engine.connect.assert_not_called()


def test_lifespan_refuses_traffic_on_bad_production_configuration(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "short")
    with pytest.raises(ValueError, match="AUTH_RATE_LIMIT_SECRET"):
        with TestClient(app):
            pass


def test_local_mode_keeps_health_available_without_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://127.0.0.1:5173")
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    attempt_protocol_enabled.cache_clear()
    monkeypatch.setattr(startup, "get_engine", lambda: (_ for _ in ()).throw(AssertionError("database opened")))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_proxy_headers_accept_only_loopback_proxy():
    api = FastAPI()

    @api.get("/client")
    def client_address(request: Request):
        return {"ip": request.client.host}

    wrapped = ProxyHeadersMiddleware(api, trusted_hosts=["127.0.0.1"])
    with TestClient(wrapped, client=("127.0.0.1", 1234)) as trusted:
        assert trusted.get("/client", headers={"X-Forwarded-For": "192.0.2.10"}).json() == {"ip": "192.0.2.10"}
    with TestClient(wrapped, client=("198.51.100.5", 1234)) as untrusted:
        assert untrusted.get("/client", headers={"X-Forwarded-For": "192.0.2.10"}).json() == {"ip": "198.51.100.5"}
