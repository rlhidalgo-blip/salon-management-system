"""Read-only capability contract; no PostgreSQL connection or financial writes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.transactions import options_router, router as transaction_router
from app.modules.transactions.attempt_feature import attempt_protocol_enabled


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    attempt_protocol_enabled.cache_clear()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(options_router.router)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "owner", "Owner", "synthetic")
    try:
        with TestClient(app) as client:
            yield client, app
    finally:
        attempt_protocol_enabled.cache_clear()


@pytest.mark.parametrize("role", ["Owner", "Cashier"])
@pytest.mark.parametrize("flag,expected", [("0", "legacy"), ("1", "reserved_v1")])
def test_authenticated_capability_uses_writer_switch(api, monkeypatch, role, flag, expected):
    client, app = api
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", flag)
    attempt_protocol_enabled.cache_clear()
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic", role, "synthetic")
    response = client.get("/api/v1/sales/capabilities")
    assert response.status_code == 200
    assert response.json() == {"protocol": expected}
    assert response.headers["Cache-Control"] == "no-store"
    assert options_router.attempt_protocol_enabled is transaction_router.attempt_protocol_enabled
    assert set(response.json()) == {"protocol"}


def test_capability_requires_session(api):
    client, app = api
    del app.dependency_overrides[get_current_principal]
    response = client.get("/api/v1/sales/capabilities")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_unknown_role_is_forbidden(api):
    client, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(3, "synthetic", "Unknown", "synthetic")
    response = client.get("/api/v1/sales/capabilities")
    assert response.status_code == 403


def test_invalid_flag_fails_closed(api, monkeypatch):
    client, _app = api
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "unexpected")
    attempt_protocol_enabled.cache_clear()
    with pytest.raises(RuntimeError, match="SALE_ATTEMPT_PROTOCOL_ENABLED"):
        attempt_protocol_enabled()
