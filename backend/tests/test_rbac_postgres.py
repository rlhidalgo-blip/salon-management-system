"""Opt-in RBAC probes on yabs_salon_test; no probe routes enter production."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, insert, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import install_error_handlers
from app.core.security import hash_password
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_owner,
    require_owner_or_cashier,
)
from app.modules.auth.models import AuthSession
from app.modules.auth.router import router as auth_router
from app.modules.users.models import User


ORIGIN = "http://localhost"
PASSWORD = "synthetic-rbac-password"


def _probe_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(auth_router)

    @app.get("/probe/owner")
    def owner(principal: Principal = Depends(require_owner), again: Principal = Depends(get_current_principal)):
        assert principal is again
        return {"role": principal.role}

    @app.get("/probe/shared")
    def shared(principal: Principal = Depends(require_owner_or_cashier)):
        return {"role": principal.role}

    @app.post("/probe/owner-change")
    def owner_change(principal: Principal = Depends(require_owner)):
        return {"role": principal.role}

    return app


class RbacCase:
    def __init__(self, connection, client: TestClient, marker: str) -> None:
        self.connection = connection
        self.client = client
        self.marker = marker
        self.user_ids: set[int] = set()

    def user(self, role: str) -> tuple[int, str]:
        username = f"{self.marker}-{role.lower()}"
        user_id = self.connection.execute(
            insert(User).values(username=username, password_hash=hash_password(PASSWORD), role=role, active=True)
            .returning(User.id)
        ).scalar_one()
        self.user_ids.add(user_id)
        return user_id, username

    def login(self, username: str):
        response = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        return response


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[RbacCase]:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL RBAC tests")
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
            revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            has_attempts = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
            if (revision, has_attempts) not in (("20261020_01", False), ("20261027_01", True)):
                pytest.fail("Expected migration revision absent; no writes attempted")
            baseline_sessions = connection.scalar(select(func.count()).select_from(AuthSession))
            baseline_audits = connection.scalar(select(func.count()).select_from(AuditEvent))
            connection.rollback()
            outer = connection.begin()
            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
            app = _probe_app()

            def session_override():
                with Session(
                    bind=connection, autoflush=False, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            with TestClient(app, base_url=ORIGIN) as client:
                case = RbacCase(connection, client, f"integration-rbac-{uuid4().hex}")
                try:
                    yield case
                finally:
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


def test_owner_cashier_and_request_cached_authentication(api: RbacCase) -> None:
    _, owner_name = api.user("Owner")
    _, cashier_name = api.user("Cashier")
    api.login(owner_name)
    commits: list[int] = []

    def after_commit(session: Session) -> None:
        commits.append(1)

    event.listen(Session, "after_commit", after_commit)
    try:
        assert api.client.get("/probe/owner").status_code == 200
        assert len(commits) == 1  # Both dependencies shared one validation/refresh.
    finally:
        event.remove(Session, "after_commit", after_commit)
    assert api.client.get("/probe/shared").status_code == 200
    api.login(cashier_name)
    denied = api.client.get("/probe/owner")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
    assert api.client.get("/probe/shared").status_code == 200


def test_missing_invalid_expired_and_revoked_sessions_return_401(api: RbacCase) -> None:
    assert api.client.get("/probe/shared").status_code == 401
    api.client.cookies.set("salon_session_dev", "invalid-token")
    assert api.client.get("/probe/shared").status_code == 401

    user_id, username = api.user("Owner")
    api.login(username)
    api.connection.execute(
        update(AuthSession).where(AuthSession.user_id == user_id)
        .values(expires_at=func.clock_timestamp() - text("INTERVAL '1 second'"))
    )
    assert api.client.get("/probe/shared").status_code == 401
    api.connection.execute(
        update(AuthSession).where(AuthSession.user_id == user_id)
        .values(expires_at=func.clock_timestamp() + text("INTERVAL '1 hour'"), revoked_at=func.clock_timestamp())
    )
    assert api.client.get("/probe/shared").status_code == 401


def test_role_change_deactivation_and_post_guards(api: RbacCase) -> None:
    user_id, username = api.user("Owner")
    login = api.login(username)
    csrf = login.json()["csrf_token"]
    assert api.client.post(
        "/probe/owner-change", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    ).status_code == 200
    assert api.client.post("/probe/owner-change", headers={"Origin": ORIGIN}).status_code == 403
    assert api.client.post("/probe/owner-change", headers={"X-CSRF-Token": csrf}).status_code == 403

    api.connection.execute(update(User).where(User.id == user_id).values(role="Cashier"))
    assert api.client.get("/probe/owner").status_code == 403
    assert api.client.get("/probe/shared").status_code == 200
    assert api.client.get("/api/v1/auth/me").json()["user"]["role"] == "Cashier"
    api.connection.execute(update(User).where(User.id == user_id).values(active=False))
    assert api.client.get("/probe/owner").status_code == 401
    assert api.client.get("/probe/shared").status_code == 401
