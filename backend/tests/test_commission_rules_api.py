"""Fast commission API tests; SQLite is not PostgreSQL constraint enforcement."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB, dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.commissions.router import router
from app.core.exceptions import ApiError
from app.modules.commissions.service import _lock_rule, lock_rule_for_catalog_assignment
from app.modules.users.models import User


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(BigInteger, "sqlite")
def compile_bigint_for_sqlite(_type, _compiler, **_kw):
    # SQLite auto-generates a primary key only when its declared type is INTEGER.
    return "INTEGER"


@pytest.fixture
def api() -> Iterator[tuple[FastAPI, object]]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (User, CommissionRule, Service, Product, AuditEvent):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(User(id=1, username="synthetic", password_hash="synthetic-no-login", role="Owner"))
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic", "Owner", "synthetic")
    try:
        yield app, factory
    finally:
        engine.dispose()


def create(client: TestClient, name="Haircut", type="Percentage", value="50.00"):
    return client.post("/api/v1/commission-rules", json={"name": name, "type": type, "value": value})


def test_lifecycle_and_audit(api) -> None:
    app, factory = api
    with TestClient(app) as client:
        assert client.get("/api/v1/commission-rules").json() == []
        first = create(client, "  Haircut  ")
        assert first.status_code == 201
        record = first.json()
        assert record == {"id": record["id"], "name": "Haircut", "type": "Percentage", "value": "50.00", "active": True}
        second = create(client, "Product credit", "Fixed", "25.50")
        assert second.status_code == 201
        assert [row["id"] for row in client.get("/api/v1/commission-rules").json()] == [record["id"], second.json()["id"]]
        path = f"/api/v1/commission-rules/{record['id']}/status"
        assert client.patch(path, json={"active": False}).json() == {**record, "active": False}
        assert client.patch(path, json={"active": True}).json() == record
        assert client.patch(path, json={"active": True}).status_code == 200
        assert client.patch("/api/v1/commission-rules/999/status", json={"active": False}).status_code == 404
        assert client.patch(f"/api/v1/commission-rules/{record['id']}", json={"value": "40"}).status_code == 404
        assert client.delete(f"/api/v1/commission-rules/{record['id']}").status_code == 404
    with factory() as session:
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.id)))
        assert [row.event_type for row in events] == [
            "CommissionRuleCreated", "CommissionRuleCreated", "CommissionRuleStatusChanged", "CommissionRuleStatusChanged",
        ]
        assert all(row.actor_user_id == 1 and row.outcome == "Success" for row in events)
        assert session.get(CommissionRule, record["id"]).value == Decimal("50.00")


@pytest.mark.parametrize("payload", [
    {"name": " ", "type": "Percentage", "value": "50"},
    {"name": "A", "type": "Other", "value": "50"},
    {"name": "A", "type": "Percentage", "value": "0"},
    {"name": "A", "type": "Percentage", "value": "100.01"},
    {"name": "A", "type": "Fixed", "value": "-1"},
    {"name": "A", "type": "Fixed", "value": "1.001"},
    {"name": "A", "type": "Fixed", "value": "12345678901.00"},
    {"name": "A", "type": "Fixed", "value": "5", "active": False},
])
def test_create_validation(api, payload) -> None:
    app, _factory = api
    with TestClient(app) as client:
        response = client.post("/api/v1/commission-rules", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("payload", [{}, {"active": "false"}, {"active": 0}, {"active": False, "value": "10"}])
def test_status_strict_boolean(api, payload) -> None:
    app, _factory = api
    with TestClient(app) as client:
        rule_id = create(client).json()["id"]
        response = client.patch(f"/api/v1/commission-rules/{rule_id}/status", json=payload)
        assert response.status_code == 422
        assert client.get("/api/v1/commission-rules").json()[0]["active"] is True


def test_references_and_conflict_rollback(api) -> None:
    app, factory = api
    with TestClient(app) as client:
        rule_id = create(client).json()["id"]
        fixed_rule_id = create(client, "Product commission", "Fixed", "10.00").json()["id"]
        with factory.begin() as session:
            session.add_all([
                Service(name="Synthetic service", current_price=Decimal("100"), commission_rule_id=rule_id, active=True),
                Service(name="Another service", current_price=Decimal("100"), commission_rule_id=rule_id, active=True),
                Product(name="Synthetic product", current_price=Decimal("100"), commission_rule_id=fixed_rule_id, active=True),
            ])
        path = f"/api/v1/commission-rules/{rule_id}/status"
        fixed_path = f"/api/v1/commission-rules/{fixed_rule_id}/status"
        conflict = client.patch(path, json={"active": False})
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "rule_in_use"
        assert client.patch(fixed_path, json={"active": False}).status_code == 409
        with factory.begin() as session:
            assert session.get(CommissionRule, rule_id).active is True
            assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "CommissionRuleStatusChanged")) is None
            session.scalar(select(Service).where(Service.name == "Synthetic service")).active = False
        assert client.patch(path, json={"active": False}).status_code == 409
        with factory.begin() as session:
            for item in session.scalars(select(Product)):
                item.active = False
        assert client.patch(fixed_path, json={"active": False}).status_code == 200
        assert client.patch(path, json={"active": False}).status_code == 409
        with factory.begin() as session:
            for item in session.scalars(select(Service)):
                item.active = False
        assert client.patch(path, json={"active": False}).status_code == 200
        assert all(not row["active"] for row in client.get("/api/v1/commission-rules").json())


def test_audit_failure_rolls_back_rule(api) -> None:
    app, factory = api
    engine = factory.kw["bind"]

    def fail_audit(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("synthetic audit failure")

    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = create(client)
            assert response.status_code == 500
            assert response.json()["error"]["code"] == "server_error"
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)
    with factory() as session:
        assert session.scalar(select(CommissionRule)) is None
        assert session.scalar(select(AuditEvent)) is None


def test_rbac_and_missing_session(api) -> None:
    app, _factory = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "synthetic", "Cashier", "synthetic")
    with TestClient(app) as client:
        assert client.get("/api/v1/commission-rules").status_code == 403
        assert create(client).status_code == 403
        assert client.patch("/api/v1/commission-rules/1/status", json={"active": False}).status_code == 403
    app.dependency_overrides.pop(get_current_principal)
    with TestClient(app) as client:
        assert client.get("/api/v1/commission-rules").status_code == 401
        assert create(client).status_code == 401


def test_lock_statement_is_postgres_for_update() -> None:
    class CaptureSession:
        def scalar(self, statement):
            assert "FOR UPDATE" in str(statement.compile(dialect=dialect()))
            return CommissionRule(id=1, name="Synthetic", type="Percentage", value=Decimal("50"), active=True)

    assert _lock_rule(CaptureSession(), 1).id == 1


def test_catalog_assignment_helper_rejects_inactive_rule() -> None:
    class CaptureSession:
        def __init__(self, active):
            self.active = active

        def scalar(self, statement):
            assert "FOR UPDATE" in str(statement.compile(dialect=dialect()))
            return CommissionRule(id=1, name="Synthetic", type="Percentage", value=Decimal("50"), active=self.active)

    assert lock_rule_for_catalog_assignment(CaptureSession(True), 1).id == 1
    with pytest.raises(ApiError) as exc:
        lock_rule_for_catalog_assignment(CaptureSession(False), 1)
    assert exc.value.status_code == 409
