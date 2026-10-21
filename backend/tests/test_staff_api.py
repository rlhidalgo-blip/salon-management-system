"""In-memory API tests; no PostgreSQL connection or real salon records."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.staff.models import Staff
from app.modules.staff.router import router as staff_router


@pytest.fixture
def app() -> Iterator[FastAPI]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Staff.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    api = FastAPI()
    install_error_handlers(api)
    api.include_router(staff_router)

    def session_override():
        with factory() as session:
            yield session

    api.dependency_overrides[get_db_session] = session_override
    api.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic", "Owner", "synthetic")
    try:
        yield api
    finally:
        engine.dispose()


def test_create_list_deactivate_reactivate_preserves_record(app: FastAPI) -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/staff").json() == []
        created = client.post("/api/v1/staff", json={"name": "  Sample Stylist  ", "role": "Stylist"})
        assert created.status_code == 201
        first = created.json()
        assert first == {"id": first["id"], "name": "Sample Stylist", "role": "Stylist", "active": True}

        second = client.post("/api/v1/staff", json={"name": "Sample Barber", "role": "Barber"})
        assert second.status_code == 201
        listed = client.get("/api/v1/staff")
        assert listed.status_code == 200
        assert [entry["id"] for entry in listed.json()] == [first["id"], second.json()["id"]]

        inactive = client.patch(f"/api/v1/staff/{first['id']}/status", json={"active": False})
        assert inactive.status_code == 200
        assert inactive.json() == {**first, "active": False}
        assert any(entry["id"] == first["id"] and not entry["active"] for entry in client.get("/api/v1/staff").json())

        active = client.patch(f"/api/v1/staff/{first['id']}/status", json={"active": True})
        assert active.status_code == 200
        assert active.json() == first


@pytest.mark.parametrize("payload", [
    {"name": "   ", "role": "Barber"},
    {"name": "Sample", "role": "Cashier"},
    {"name": "Sample", "role": "Barber", "active": False},
    {"name": None, "role": "Stylist"},
])
def test_create_rejects_invalid_fields(app: FastAPI, payload: dict) -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/staff", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("payload", [
    {},
    {"active": "false"},
    {"active": None},
    {"active": False, "name": "Changed"},
    {"role": "Barber"},
])
def test_status_accepts_only_strict_boolean(app: FastAPI, payload: dict) -> None:
    with TestClient(app) as client:
        created = client.post("/api/v1/staff", json={"name": "Sample", "role": "Barber"}).json()
        response = client.patch(f"/api/v1/staff/{created['id']}/status", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert client.get("/api/v1/staff").json() == [created]


def test_unknown_id_and_no_edit_or_delete_routes(app: FastAPI) -> None:
    with TestClient(app) as client:
        unknown = client.patch("/api/v1/staff/999/status", json={"active": False})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "not_found"
        assert client.patch("/api/v1/staff/999", json={"name": "Changed"}).status_code == 404
        assert client.delete("/api/v1/staff/999").status_code == 404


def test_cashier_cannot_access_any_staff_endpoint(app: FastAPI) -> None:
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "synthetic", "Cashier", "synthetic")
    with TestClient(app) as client:
        responses = (
            client.get("/api/v1/staff"),
            client.post("/api/v1/staff", json={"name": "Sample", "role": "Barber"}),
            client.patch("/api/v1/staff/1/status", json={"active": False}),
        )
    assert all(response.status_code == 403 for response in responses)
    assert all(response.json()["error"]["code"] == "forbidden" for response in responses)


def test_missing_session_returns_401(app: FastAPI) -> None:
    app.dependency_overrides.pop(get_current_principal)
    with TestClient(app) as client:
        responses = (
            client.get("/api/v1/staff"),
            client.post("/api/v1/staff", json={"name": "Sample", "role": "Barber"}),
            client.patch("/api/v1/staff/1/status", json={"active": False}),
        )
    assert all(response.status_code == 401 for response in responses)
