"""Authentication API checks that never connect to PostgreSQL."""

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.security import csrf_token_for_session, verify_csrf_token
from app.db.session import get_db_session
from app.main import app
from app.modules.auth.rate_limit import login_keys


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://localhost")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
    app.dependency_overrides[get_db_session] = lambda: None
    try:
        with TestClient(app, base_url="http://localhost") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_csrf_is_session_bound_and_constant_time_checked() -> None:
    first = csrf_token_for_session("synthetic-token-one")
    second = csrf_token_for_session("synthetic-token-two")
    assert first != second
    assert len(first) == 64
    assert verify_csrf_token("synthetic-token-one", first)
    assert not verify_csrf_token("synthetic-token-one", second)
    assert not verify_csrf_token("synthetic-token-one", None)


def test_missing_and_untrusted_post_origins_fail_closed(client: TestClient) -> None:
    payload = {"username": "synthetic", "password": "synthetic"}
    for headers in ({}, {"Origin": "https://attacker.example"}):
        response = client.post("/api/v1/auth/login", json=payload, headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_rejected"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert "set-cookie" not in response.headers


def test_validation_error_does_not_echo_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "synthetic", "password": {"secret": "do-not-echo"}},
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] is None
    assert "do-not-echo" not in response.text


def test_rate_identifiers_are_pseudonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
    keys = login_keys("Synthetic User", "127.0.0.1")
    assert keys.account == login_keys("synthetic user", "127.0.0.1").account
    assert keys.account != "Synthetic User"
    assert keys.ip != "127.0.0.1"
    assert len(keys.account) == len(keys.ip) == 64


def test_auth_api_config_rejects_insecure_production_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "production")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://salon.example")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
    with pytest.raises(ValueError, match="HTTPS"):
        config.get_auth_api_config()
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "https://salon.example")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "short")
    with pytest.raises(ValueError, match="AUTH_RATE_LIMIT_SECRET"):
        config.get_auth_api_config()
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "replace_with_at_least_32_random_bytes_before_running_auth")
    with pytest.raises(ValueError, match="AUTH_RATE_LIMIT_SECRET"):
        config.get_auth_api_config()
