"""Opt-in PostgreSQL API tests: yabs_salon_test only, outer rollback.

Savepoint-backed handler commits do not prove durable cross-connection writes.
Full assignment/deactivation race tests require the future Catalog write service.
"""

import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.security import hash_password
from app.db.session import get_db_session
from app.main import app
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.users.models import User


ORIGIN = "http://localhost"
PASSWORD = "synthetic-commission-test-password"


class Case:
    def __init__(self, connection, engine, client: TestClient, marker: str, baseline_rule_id: int | None):
        self.connection = connection
        self.engine = engine
        self.client = client
        self.marker = marker
        self.baseline_rule_id = baseline_rule_id
        self.created_ids: set[int] = set()

    def login_as(self, role: str) -> str:
        username = f"{self.marker}-{role.lower()}"
        self.connection.execute(insert(User).values(
            username=username, password_hash=hash_password(PASSWORD), role=role, active=True,
        ))
        response = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD}, headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        return response.json()["csrf_token"]

    @staticmethod
    def headers(csrf: str) -> dict[str, str]:
        return {"Origin": ORIGIN, "X-CSRF-Token": csrf}

    def create(self, csrf: str, *, type: str = "Percentage", value: str = "50.00"):
        response = self.client.post(
            "/api/v1/commission-rules",
            json={"name": f"{self.marker}-{type}-{len(self.created_ids)}", "type": type, "value": value},
            headers=self.headers(csrf),
        )
        if response.status_code == 201:
            self.created_ids.add(response.json()["id"])
        return response


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL integration tests")

    url = get_database_url()
    if url.database != "yabs_salon_test" or url.host not in ("localhost", "127.0.0.1") or url.username != "yabs_app":
        pytest.fail("Configured target is not local yabs_salon_test using yabs_app; no writes attempted")
    engine = create_engine(url)
    models = (User, AuthSession, AuditEvent, CommissionRule, Service, Product)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Connected database is not yabs_salon_test; no writes attempted")
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                pytest.fail("Alembic revision table absent; no writes attempted")
            revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            has_attempts = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
            if (revision, has_attempts) not in (("20261020_01", False), ("20261027_01", True)):
                pytest.fail("Expected revision absent; no writes attempted")
            baseline = {model: connection.scalar(select(func.count()).select_from(model)) for model in models}
            baseline_rule_id = connection.scalar(select(CommissionRule.id).order_by(CommissionRule.id).limit(1))
            connection.rollback()
            outer = connection.begin()
            monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
            monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
            monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")

            def session_override():
                with Session(bind=connection, autoflush=False, expire_on_commit=False,
                             join_transaction_mode="create_savepoint") as session:
                    yield session

            app.dependency_overrides[get_db_session] = session_override
            case = None
            try:
                with TestClient(app, base_url=ORIGIN) as client:
                    case = Case(connection, engine, client, f"commission-test-{uuid4().hex}", baseline_rule_id)
                    yield case
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                if not outer.is_active:
                    pytest.fail("Outer transaction ended unexpectedly; rollback safety lost")
                outer.rollback()

        with engine.connect() as verifier:
            if verifier.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Rollback check connected to wrong database")
            for model in models:
                assert verifier.scalar(select(func.count()).select_from(model)) == baseline[model]
            if case is not None and case.created_ids:
                assert verifier.scalar(select(func.count()).select_from(CommissionRule).where(
                    CommissionRule.id.in_(case.created_ids))) == 0
    finally:
        engine.dispose()


def test_create_list_status_and_audit(api: Case) -> None:
    csrf = api.login_as("Owner")
    initial_count = len(api.client.get("/api/v1/commission-rules").json())
    created = api.create(csrf)
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert created.json()["value"] == "50.00"
    assert created.json()["active"] is True
    assert len(api.client.get("/api/v1/commission-rules").json()) == initial_count + 1
    path = f"/api/v1/commission-rules/{rule_id}/status"
    assert api.client.patch(path, json={"active": False}, headers=api.headers(csrf)).status_code == 200
    assert api.client.patch(path, json={"active": True}, headers=api.headers(csrf)).status_code == 200
    events = list(api.connection.execute(select(AuditEvent.event_type, AuditEvent.outcome, AuditEvent.actor_user_id).where(
        AuditEvent.resource_type == "commission_rule", AuditEvent.resource_id == str(rule_id),
    ).order_by(AuditEvent.id)))
    assert [event.event_type for event in events] == [
        "CommissionRuleCreated", "CommissionRuleStatusChanged", "CommissionRuleStatusChanged",
    ]
    assert all(event.outcome == "Success" and event.actor_user_id is not None for event in events)


def test_active_shared_references_block_and_inactive_refs_allow(api: Case) -> None:
    csrf = api.login_as("Owner")
    service_rule_id = api.create(csrf).json()["id"]
    product_rule_id = api.create(csrf, type="Fixed", value="10.50").json()["id"]
    first_id = api.connection.execute(insert(Service).values(
        name=f"{api.marker}-service-1", current_price=Decimal("100"),
        commission_rule_id=service_rule_id, active=True,
    ).returning(Service.id)).scalar_one()
    api.connection.execute(insert(Service).values(
        name=f"{api.marker}-service-2", current_price=Decimal("100"),
        commission_rule_id=service_rule_id, active=True,
    ))
    api.connection.execute(insert(Product).values(
        name=f"{api.marker}-product", current_price=Decimal("100"),
        commission_rule_id=product_rule_id, active=True,
    ))
    service_path = f"/api/v1/commission-rules/{service_rule_id}/status"
    product_path = f"/api/v1/commission-rules/{product_rule_id}/status"
    assert api.client.patch(service_path, json={"active": False}, headers=api.headers(csrf)).status_code == 409
    assert api.client.patch(product_path, json={"active": False}, headers=api.headers(csrf)).status_code == 409
    assert api.connection.scalar(select(CommissionRule.active).where(CommissionRule.id == service_rule_id)) is True
    assert api.connection.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.resource_type == "commission_rule", AuditEvent.resource_id == str(service_rule_id),
        AuditEvent.event_type == "CommissionRuleStatusChanged",
    )) == 0
    api.connection.execute(text("UPDATE services SET active = false WHERE id = :id"), {"id": first_id})
    assert api.client.patch(service_path, json={"active": False}, headers=api.headers(csrf)).status_code == 409
    api.connection.execute(text("UPDATE services SET active = false WHERE commission_rule_id = :id"), {"id": service_rule_id})
    api.connection.execute(text("UPDATE products SET active = false WHERE commission_rule_id = :id"), {"id": product_rule_id})
    assert api.client.patch(service_path, json={"active": False}, headers=api.headers(csrf)).status_code == 200
    assert api.client.patch(product_path, json={"active": False}, headers=api.headers(csrf)).status_code == 200


def test_security_validation_and_no_mutation_on_error(api: Case) -> None:
    assert api.client.get("/api/v1/commission-rules").status_code == 401
    csrf = api.login_as("Owner")
    payload = {"name": f"{api.marker}-guard", "type": "Percentage", "value": "50.00"}
    assert api.client.post("/api/v1/commission-rules", json=payload,
                           headers={"X-CSRF-Token": csrf}).status_code == 403
    assert api.client.post("/api/v1/commission-rules", json=payload,
                           headers={"Origin": ORIGIN}).status_code == 403
    assert api.client.post("/api/v1/commission-rules", json={**payload, "value": "100.01"},
                           headers=api.headers(csrf)).status_code == 422
    guarded_rule_id = api.create(csrf).json()["id"]
    guarded_path = f"/api/v1/commission-rules/{guarded_rule_id}/status"
    assert api.client.patch(guarded_path, json={"active": False},
                            headers={"X-CSRF-Token": csrf}).status_code == 403
    assert api.client.patch(guarded_path, json={"active": False},
                            headers={"Origin": ORIGIN}).status_code == 403
    assert api.connection.scalar(select(CommissionRule.active).where(CommissionRule.id == guarded_rule_id)) is True
    assert api.client.patch("/api/v1/commission-rules/999999999/status", json={"active": False},
                            headers=api.headers(csrf)).status_code == 404
    assert api.connection.scalar(select(func.count()).select_from(CommissionRule).where(
        CommissionRule.name == payload["name"])) == 0
    cashier_csrf = api.login_as("Cashier")
    assert api.client.get("/api/v1/commission-rules").status_code == 403
    assert api.client.post("/api/v1/commission-rules", json=payload,
                           headers=api.headers(cashier_csrf)).status_code == 403
    assert api.client.patch("/api/v1/commission-rules/999999999/status", json={"active": False},
                            headers=api.headers(cashier_csrf)).status_code == 403


def test_postgres_row_lock_conflicts_when_baseline_rule_exists(api: Case) -> None:
    if api.baseline_rule_id is None:
        pytest.skip("No pre-existing test rule: rollback-only synthetic rows are invisible to a second connection")
    # Read-only lock check on isolated test DB; no catalog writes or rule changes.
    rule_id = api.baseline_rule_id
    api.connection.scalar(select(CommissionRule.id).where(CommissionRule.id == rule_id).with_for_update())
    with api.engine.connect() as second:
        assert second.scalar(text("SELECT current_database()")) == "yabs_salon_test"
        try:
            with pytest.raises(OperationalError) as exc:
                second.scalar(select(CommissionRule.id).where(CommissionRule.id == rule_id).with_for_update(nowait=True))
            assert exc.value.orig.sqlstate == "55P03"  # lock_not_available
        finally:
            second.rollback()
