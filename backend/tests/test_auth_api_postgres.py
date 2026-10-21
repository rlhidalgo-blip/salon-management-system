"""Opt-in API tests: real handler commits release savepoints, not the outer transaction.

These prove application ordering, NOT durable commit or cross-connection
visibility. Both remain required controlled tests before production.
"""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, insert, select, text, update
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.core.security import hash_password
from app.db.session import get_db_session
from app.main import app
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.users.models import User
from app.core.config import get_database_url


ORIGIN = "http://localhost"
PASSWORD = "synthetic-test-password"


class ApiCase:
    def __init__(self, connection, client: TestClient, marker: str) -> None:
        self.connection = connection
        self.client = client
        self.marker = marker
        self.user_ids: set[int] = set()

    def user(self, role: str = "Owner", active: bool = True) -> tuple[int, str]:
        username = f"{self.marker}-{role.lower()}-{len(self.user_ids)}"
        user_id = self.connection.execute(
            insert(User).values(username=username, password_hash=hash_password(PASSWORD), role=role, active=active)
            .returning(User.id)
        ).scalar_one()
        self.user_ids.add(user_id)
        return user_id, username

    def post_login(self, username: str, password: str = PASSWORD):
        return self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password},
            headers={"Origin": ORIGIN},
        )


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiCase]:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL API tests")

    url = get_database_url()
    if url.database != "yabs_salon_test":
        pytest.fail("Configured database is not yabs_salon_test; no writes attempted")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Connected database is not yabs_salon_test; no writes attempted")
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                pytest.fail("Alembic version table absent; no writes attempted")
            if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01":
                pytest.fail("Expected migration revision absent; no writes attempted")
            baseline_audits = connection.scalar(select(func.count()).select_from(AuditEvent))
            baseline_sessions = connection.scalar(select(func.count()).select_from(AuthSession))
            connection.rollback()
            outer = connection.begin()

            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")

            def session_override():
                with Session(
                    bind=connection, autoflush=False, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            try:
                with TestClient(app, base_url=ORIGIN) as client:
                    case = ApiCase(connection, client, f"integration-api-{uuid4().hex}")
                    yield case
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                if not outer.is_active:
                    pytest.fail("Outer transaction ended unexpectedly; rollback safety lost")
                outer.rollback()

        with engine.connect() as verifier:
            if verifier.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Rollback check connected to wrong database")
            if case.user_ids:
                assert verifier.scalar(select(func.count()).select_from(User).where(User.id.in_(case.user_ids))) == 0
            assert verifier.scalar(select(func.count()).select_from(AuthSession)) == baseline_sessions
            assert verifier.scalar(select(func.count()).select_from(AuditEvent)) == baseline_audits
    finally:
        engine.dispose()


def test_login_cookie_me_refresh_and_logout_commit_order(api: ApiCase, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id, username = api.user()
    events: list[str] = []

    def after_commit(session: Session) -> None:
        events.append("commit")

    original_set_cookie = Response.set_cookie
    original_delete_cookie = Response.delete_cookie

    def set_cookie(response, *args, **kwargs):
        assert events and events[-1] == "commit"
        events.append("set_cookie")
        return original_set_cookie(response, *args, **kwargs)

    def delete_cookie(response, *args, **kwargs):
        assert events and events[-1] == "commit"
        events.append("delete_cookie")
        return original_delete_cookie(response, *args, **kwargs)

    event.listen(Session, "after_commit", after_commit)
    monkeypatch.setattr(Response, "set_cookie", set_cookie)
    monkeypatch.setattr(Response, "delete_cookie", delete_cookie)
    try:
        login = api.post_login(username)
        assert login.status_code == 200
        assert events[-2:] == ["commit", "set_cookie"]
        assert login.json()["user"] == {"id": user_id, "username": username, "role": "Owner"}
        assert "salon_session_dev=" in login.headers["set-cookie"]
        assert "httponly" in login.headers["set-cookie"].lower()
        assert "samesite=lax" in login.headers["set-cookie"].lower()
        assert "path=/" in login.headers["set-cookie"].lower()
        assert "secure" not in login.headers["set-cookie"].lower()
        stored_hash = api.connection.scalar(select(AuthSession.token_hash).where(AuthSession.user_id == user_id))
        assert len(stored_hash) == 64
        assert stored_hash not in login.headers["set-cookie"]

        initial_expiry = api.connection.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == user_id))
        before_me = len(events)
        me = api.client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["role"] == "Owner"
        assert events[before_me:] == ["commit"]
        refreshed_expiry = api.connection.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == user_id))
        assert refreshed_expiry >= initial_expiry

        # Starlette implements delete_cookie by calling set_cookie internally.
        monkeypatch.setattr(Response, "set_cookie", original_set_cookie)
        before_logout = len(events)
        logout = api.client.post(
            "/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": me.json()["csrf_token"]},
        )
        assert logout.status_code == 204
        assert events[before_logout:] == ["commit", "delete_cookie"]
        assert "Max-Age=0" in logout.headers["set-cookie"]
        assert api.connection.scalar(select(AuthSession.revoked_at).where(AuthSession.user_id == user_id)) is not None
        assert api.client.get("/api/v1/auth/me").status_code == 401
    finally:
        event.remove(Session, "after_commit", after_commit)


def test_login_failures_are_generic_and_audited_after_handler_commit(api: ApiCase) -> None:
    _, active_name = api.user()
    _, inactive_name = api.user(active=False)
    for username, password in (
        (f"{api.marker}-unknown", PASSWORD),
        (active_name, "wrong-password"),
        (inactive_name, PASSWORD),
    ):
        response = api.post_login(username, password)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
        assert response.json()["error"]["message"] == "Invalid username or password"
        assert "set-cookie" not in response.headers
    failures = api.connection.execute(
        select(AuditEvent.actor_user_id, AuditEvent.event_metadata).where(AuditEvent.event_type == "LoginFailure")
    ).all()
    assert len(failures) == 3
    assert all(actor_id is None for actor_id, _ in failures)
    assert all(set(metadata) == {"account_key", "ip_key"} for _, metadata in failures)
    assert all(active_name not in str(metadata) for _, metadata in failures)
    assert all(PASSWORD not in str(metadata) for _, metadata in failures)


def test_csrf_and_origin_checks_block_logout(api: ApiCase) -> None:
    _, username = api.user()
    login = api.post_login(username)
    assert login.status_code == 200
    for headers, expected_code in (
        ({"X-CSRF-Token": login.json()["csrf_token"]}, "origin_rejected"),
        ({"Origin": "https://attacker.example", "X-CSRF-Token": login.json()["csrf_token"]}, "origin_rejected"),
        ({"Origin": ORIGIN}, "csrf_rejected"),
        ({"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, "csrf_rejected"),
    ):
        response = api.client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == expected_code
    cross_site_me = api.client.get("/api/v1/auth/me", headers={"Sec-Fetch-Site": "cross-site"})
    assert cross_site_me.status_code == 403
    assert api.client.get("/api/v1/auth/me").status_code == 200


def test_production_cookie_attributes(api: ApiCase, monkeypatch: pytest.MonkeyPatch) -> None:
    _, username = api.user()
    monkeypatch.setenv("AUTH_COOKIE_MODE", "production")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "https://localhost")
    with TestClient(app, base_url="https://localhost") as secure_client:
        response = secure_client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD},
            headers={"Origin": "https://localhost"},
        )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-salon_session=")
    assert "secure" in cookie.lower()
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "domain=" not in cookie.lower()


def test_current_role_and_disabled_account_affect_me(api: ApiCase) -> None:
    user_id, username = api.user()
    assert api.post_login(username).status_code == 200
    api.connection.execute(update(User).where(User.id == user_id).values(role="Cashier"))
    assert api.client.get("/api/v1/auth/me").json()["user"]["role"] == "Cashier"
    api.connection.execute(update(User).where(User.id == user_id).values(active=False))
    assert api.client.get("/api/v1/auth/me").status_code == 401


def test_account_and_ip_login_limits(api: ApiCase) -> None:
    username = f"{api.marker}-limited"
    for _ in range(5):
        assert api.post_login(username).status_code == 401
    limited = api.post_login(username)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"

    for index in range(15):
        assert api.post_login(f"{api.marker}-other-{index}").status_code == 401
    ip_limited = api.post_login(f"{api.marker}-other-15")
    assert ip_limited.status_code == 429
    assert api.connection.scalar(select(func.count()).select_from(AuditEvent)) == 20
