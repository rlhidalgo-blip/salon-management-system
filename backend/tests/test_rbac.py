"""Test-only probe routes for reusable RBAC dependencies; no database access."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import install_error_handlers
from app.core.security import csrf_token_for_session
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_owner,
    require_owner_or_cashier,
    require_state_change_protection,
)


def _probe_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/probe/owner")
    def owner(principal: Principal = Depends(require_owner), again: Principal = Depends(get_current_principal)):
        assert principal is again  # FastAPI must cache authentication per request.
        return {"role": principal.role}

    @app.get("/probe/shared")
    def shared(principal: Principal = Depends(require_owner_or_cashier)):
        return {"role": principal.role}

    # The unit override bypasses Principal's automatic guard, so attach it here.
    @app.post("/probe/owner-change", dependencies=[Depends(require_state_change_protection)])
    def owner_change(principal: Principal = Depends(require_owner)):
        return {"role": principal.role}

    return app


@pytest.mark.parametrize("role", ["Owner", "Cashier"])
def test_shared_access_and_owner_only_role_check(role: str) -> None:
    app = _probe_app()
    calls = []

    def principal():
        calls.append(1)
        return Principal(user_id=1, username="synthetic", role=role, csrf_token="synthetic")

    app.dependency_overrides[get_current_principal] = principal
    with TestClient(app) as client:
        shared = client.get("/probe/shared")
        owner = client.get("/probe/owner")

    assert shared.status_code == 200
    assert owner.status_code == (200 if role == "Owner" else 403)
    assert len(calls) == 2  # One validation for each request, not each dependency.
    if role == "Cashier":
        assert owner.json()["error"]["code"] == "forbidden"


def test_owner_role_does_not_replace_origin_and_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://localhost")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
    app = _probe_app()
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic", "Owner", "synthetic")
    token = "synthetic-session-token"
    with TestClient(app, base_url="http://localhost") as client:
        client.cookies.set("salon_session_dev", token)
        missing_origin = client.post("/probe/owner-change", headers={"X-CSRF-Token": csrf_token_for_session(token)})
        missing_csrf = client.post("/probe/owner-change", headers={"Origin": "http://localhost"})
        valid = client.post(
            "/probe/owner-change",
            headers={"Origin": "http://localhost", "X-CSRF-Token": csrf_token_for_session(token)},
        )

    assert missing_origin.status_code == 403
    assert missing_csrf.status_code == 403
    assert valid.status_code == 200
