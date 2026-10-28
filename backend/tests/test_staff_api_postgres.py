"""Opt-in Staff API tests; synthetic writes roll back on yabs_salon_test only."""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import install_error_handlers
from app.core.security import hash_password
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.auth.router import router as auth_router
from app.modules.staff.models import Staff
from app.modules.staff.router import router as staff_router
from app.modules.users.models import User


ORIGIN = "http://localhost"
PASSWORD = "synthetic-staff-test-password"


class StaffCase:
    def __init__(self, connection, client: TestClient, marker: str) -> None:
        self.connection = connection
        self.client = client
        self.marker = marker
        self.user_ids: set[int] = set()
        self.staff_ids: set[int] = set()

    def login_as(self, role: str) -> str:
        username = f"{self.marker}-{role.lower()}-{len(self.user_ids)}"
        user_id = self.connection.execute(
            insert(User).values(
                username=username, password_hash=hash_password(PASSWORD), role=role, active=True,
            ).returning(User.id)
        ).scalar_one()
        self.user_ids.add(user_id)
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        return response.json()["csrf_token"]

    def create_staff(self, name: str, role: str, csrf: str):
        response = self.client.post(
            "/api/v1/staff", json={"name": name, "role": role},
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        if response.status_code == 201:
            self.staff_ids.add(response.json()["id"])
        return response


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[StaffCase]:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL Staff tests")

    url = get_database_url()
    if url.database != "yabs_salon_test" or url.host not in ("localhost", "127.0.0.1") or url.username != "yabs_app":
        pytest.fail("Configured target is not the local yabs_salon_test app database; no writes attempted")
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
            models = (Staff, User, AuthSession, AuditEvent)
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in models}
            connection.rollback()
            outer = connection.begin()

            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
            app = FastAPI()
            install_error_handlers(app)
            app.include_router(auth_router)
            app.include_router(staff_router)

            def session_override():
                with Session(
                    bind=connection, autoflush=False, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            with TestClient(app, base_url=ORIGIN) as client:
                case = StaffCase(connection, client, f"integration-staff-{uuid4().hex}")
                try:
                    yield case
                finally:
                    if not outer.is_active:
                        pytest.fail("Outer transaction ended unexpectedly; rollback safety lost")
                    outer.rollback()

            with engine.connect() as verifier:
                if verifier.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                    pytest.fail("Rollback verification connected to wrong database")
                for model in models:
                    assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
                if case.staff_ids:
                    assert verifier.scalar(
                        select(func.count()).select_from(Staff).where(Staff.id.in_(case.staff_ids))
                    ) == 0
                if case.user_ids:
                    assert verifier.scalar(
                        select(func.count()).select_from(User).where(User.id.in_(case.user_ids))
                    ) == 0
    finally:
        engine.dispose()


def test_staff_lifecycle_preserves_existing_records(api: StaffCase) -> None:
    csrf = api.login_as("Owner")
    initial = api.client.get("/api/v1/staff")
    assert initial.status_code == 200
    initial_count = len(initial.json())

    first = api.create_staff(f"{api.marker}-stylist", "Stylist", csrf)
    second = api.create_staff(f"{api.marker}-barber", "Barber", csrf)
    assert first.status_code == second.status_code == 201
    first_record = first.json()
    assert first_record["active"] is True
    assert second.json()["active"] is True
    listed = api.client.get("/api/v1/staff")
    assert listed.status_code == 200
    assert len(listed.json()) == initial_count + 2
    assert [record["id"] for record in listed.json()] == sorted(record["id"] for record in listed.json())

    path = f"/api/v1/staff/{first_record['id']}/status"
    inactive = api.client.patch(
        path, json={"active": False}, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert inactive.status_code == 200
    assert inactive.json() == {**first_record, "active": False}
    assert api.connection.scalar(select(func.count()).select_from(Staff).where(Staff.id == first_record["id"])) == 1
    assert api.connection.scalar(select(Staff.active).where(Staff.id == second.json()["id"])) is True

    active = api.client.patch(
        path, json={"active": True}, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert active.status_code == 200
    assert active.json() == first_record


def test_owner_only_and_browser_guards(api: StaffCase) -> None:
    assert api.client.get("/api/v1/staff").status_code == 401
    owner_csrf = api.login_as("Owner")
    assert api.client.get("/api/v1/staff").status_code == 200
    payload = {"name": f"{api.marker}-guard", "role": "Barber"}
    missing_origin = api.client.post("/api/v1/staff", json=payload, headers={"X-CSRF-Token": owner_csrf})
    missing_csrf = api.client.post("/api/v1/staff", json=payload, headers={"Origin": ORIGIN})
    assert missing_origin.status_code == 403
    assert missing_origin.json()["error"]["code"] == "origin_rejected"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "csrf_rejected"
    created = api.create_staff(payload["name"], payload["role"], owner_csrf)
    assert created.status_code == 201
    staff_id = created.json()["id"]
    assert api.client.patch(
        f"/api/v1/staff/{staff_id}/status", json={"active": False}, headers={"Origin": ORIGIN},
    ).status_code == 403

    cashier_csrf = api.login_as("Cashier")
    assert api.client.get("/api/v1/staff").status_code == 403
    assert api.client.post(
        "/api/v1/staff", json=payload, headers={"Origin": ORIGIN, "X-CSRF-Token": cashier_csrf},
    ).status_code == 403
    assert api.client.patch(
        f"/api/v1/staff/{staff_id}/status", json={"active": False},
        headers={"Origin": ORIGIN, "X-CSRF-Token": cashier_csrf},
    ).status_code == 403
    assert api.connection.scalar(select(Staff.active).where(Staff.id == staff_id)) is True


def test_postgres_validation_unknown_id_and_no_edit_delete(api: StaffCase) -> None:
    csrf = api.login_as("Owner")
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    for payload in (
        {"name": " ", "role": "Stylist"},
        {"name": "Sample", "role": "Owner"},
        {"name": "Sample", "role": "Barber", "active": False},
    ):
        assert api.client.post("/api/v1/staff", json=payload, headers=headers).status_code == 422
    assert api.client.patch(
        "/api/v1/staff/999999999/status", json={"active": False}, headers=headers,
    ).status_code == 404
    assert api.client.patch(
        "/api/v1/staff/999999999/status", json={"active": "false"}, headers=headers,
    ).status_code == 422
    assert api.client.patch("/api/v1/staff/999999999", json={"name": "Changed"}, headers=headers).status_code == 404
    assert api.client.delete("/api/v1/staff/999999999", headers=headers).status_code == 404
