"""Isolated calendar API checks; write gate is overridden only in this test app."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.core.exceptions import ApiError
from app.core.security import csrf_token_for_session
from app.db.session import get_db_session
from app.modules.audit.models import AuditEvent
from app.modules.auth import dependencies as auth_dependencies
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.operating_days import feature, service
from app.modules.operating_days.date_lock import lock_operating_date
from app.modules.operating_days.feature import require_calendar_writes_ready
from app.modules.operating_days.models import OperatingDay
from app.modules.operating_days.router import router
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def functions(connection, _record):
        connection.create_function("BTRIM", 1, lambda value: value.strip() if value else value, deterministic=True)

    for model in (User, Transaction, TransactionItem, OperatingDay, AuditEvent):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as session:
        session.add_all([
            User(id=1, username="owner", password_hash="synthetic", role="Owner"),
            User(id=2, username="cashier", password_hash="synthetic", role="Cashier"),
        ])
    monkeypatch.setattr(service, "_database_time", lambda _session: datetime(2026, 11, 4, 15, 59, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "lock_operating_date", lambda _session, _day: None)
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "owner", "Owner", "synthetic")
    app.dependency_overrides[require_calendar_writes_ready] = lambda: None
    try:
        yield app, factory
    finally:
        engine.dispose()


def put(client, day, status, version=0, reason=None):
    return client.put(f"/api/v1/operating-days/{day}", json={
        "status": status, "closure_reason": reason, "expected_version": version,
    })


def test_four_statuses_corrections_and_audit(api, monkeypatch):
    app, factory = api
    with TestClient(app) as client:
        unknown = client.get("/api/v1/operating-days?from=2026-11-01&through=2026-11-04")
        assert unknown.status_code == 200
        assert unknown.headers["cache-control"] == "no-store"
        assert [row["status"] for row in unknown.json()] == ["Unknown"] * 4
        assert put(client, "2026-11-01", "Open").json()["version"] == 1
        assert put(client, "2026-11-02", "Closed", reason=" Holiday ").json()["closure_reason"] == "Holiday"
        assert put(client, "2026-11-06", "PlannedClosed", reason="Planned holiday").status_code == 200
        assert put(client, "2026-11-01", "Unknown", version=1).json()["version"] == 2
        assert put(client, "2026-11-01", "Open", version=2).json()["version"] == 3
        history = client.get("/api/v1/operating-days/2026-11-01/history")
        assert [row["version"] for row in history.json()] == [3, 2, 1]
        assert history.json()[0]["previous_status"] == "Unknown"
        # A plan remains unconfirmed after its date and its reason can be corrected.
        monkeypatch.setattr(service, "_database_time", lambda _session: datetime(2026, 11, 7, tzinfo=timezone.utc))
        assert put(client, "2026-11-06", "PlannedClosed", version=1,
                   reason="Corrected plan reason").json()["version"] == 2
    with factory() as session:
        assert session.get(OperatingDay, date(2026, 11, 1)).version == 3
        assert session.get(OperatingDay, date(2026, 11, 2)).status == "Closed"
        assert session.get(OperatingDay, date(2026, 11, 6)).status == "PlannedClosed"
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.id)))
        assert len(events) == 6
        assert all(row.actor_user_id == 1 and row.outcome == "Success" for row in events)


def test_validation_versions_and_manila_midnight(api, monkeypatch):
    app, factory = api
    with TestClient(app) as client:
        for status, reason in (("Closed", None), ("PlannedClosed", " "), ("Open", "extra"),
                               ("Closed", "x" * 501), ("Other", None)):
            assert put(client, "2026-11-03", status, reason=reason).status_code == 422
        assert put(client, "2026-11-05", "Open").status_code == 422
        assert put(client, "2026-11-04", "PlannedClosed", reason="Later").status_code == 422
        assert put(client, "2026-11-04", "Open").status_code == 200
        assert put(client, "2026-11-04", "Closed", version=0, reason="Stale").json()["error"]["code"] == "operating_day_changed"
        assert put(client, "2026-02-30", "Open").status_code == 422
        assert client.get("/api/v1/operating-days?from=2026-11-31&through=2026-12-01").status_code == 422
        assert client.get("/api/v1/operating-days?from=2026-11-04&through=2026-11-03").status_code == 422
        assert client.get("/api/v1/operating-days?from=2026-01-01&through=2026-11-04").status_code == 422
        assert client.get("/api/v1/operating-days/2026-11-01/history?limit=101").status_code == 422
        monkeypatch.setattr(service, "_database_time", lambda _session: datetime(2026, 11, 4, 16, tzinfo=timezone.utc))
        assert put(client, "2026-11-05", "Open").status_code == 200
    with factory() as session:
        assert session.get(OperatingDay, date(2026, 11, 4)).status == "Open"


def test_completed_conflict_and_voided_sale_excluded_from_gross(api):
    app, factory = api
    with factory.begin() as session:
        session.add_all([
            Transaction(id=1, business_date=date(2026, 11, 1), recorded_by_user_id=1,
                        entry_source="Direct", payment_method="Cash", status="Completed"),
            Transaction(id=2, business_date=date(2026, 11, 2), recorded_by_user_id=1,
                        entry_source="Direct", payment_method="Cash", status="Voided",
                        void_reason="Mistake", voided_by_user_id=1,
                        voided_at=datetime(2026, 11, 3, tzinfo=timezone.utc)),
        ])
    with TestClient(app) as client:
        conflict = put(client, "2026-11-01", "Closed", reason="Mistake")
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "completed_sales_on_date"
        assert put(client, "2026-11-02", "Closed", reason="Closed").status_code == 200
        rows = client.get("/api/v1/operating-days?from=2026-11-01&through=2026-11-02").json()
        assert rows[0]["completed_transaction_count"] == 1
        assert rows[0]["gross_sales"] == "0.00"
        assert rows[1]["completed_transaction_count"] == 0
        assert rows[1]["gross_sales"] == "0.00"
    with factory() as session:
        assert session.get(OperatingDay, date(2026, 11, 1)) is None
        assert session.get(Transaction, 1).status == "Completed"


def test_bulk_atomicity_selection_and_audit(api):
    app, factory = api
    with TestClient(app) as client:
        dates = [{"business_date": "2026-11-01", "expected_version": 0},
                 {"business_date": "2026-11-02", "expected_version": 0}]
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": dates}).json()["changed_count"] == 2
        failed = client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
            {"business_date": "2026-11-03", "expected_version": 0},
            {"business_date": "2026-11-02", "expected_version": 0},
        ]})
        assert failed.status_code == 409
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": dates}).status_code == 409
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [dates[0], dates[0]]}).status_code == 422
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
            {"business_date": "2026-11-04", "expected_version": 0},
        ]}).status_code == 422
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
            {"business_date": "2026-11-03", "expected_version": 0},
        ] * 91}).status_code == 422
    with factory() as session:
        assert session.get(OperatingDay, date(2026, 11, 3)) is None
        assert session.scalar(select(AuditEvent).where(AuditEvent.resource_id == "2026-11-03")) is None
        events = list(session.scalars(select(AuditEvent)))
        assert len(events) == 2 and all(row.event_metadata["bulk"] for row in events)


def test_bulk_audit_failure_rolls_back_every_date(api):
    app, factory = api
    engine = factory.kw["bind"]
    calls = 0

    def fail_second_audit(_conn, _cursor, statement, _params, _context, _many):
        nonlocal calls
        if statement.startswith("INSERT INTO audit_events"):
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic audit failure")

    event.listen(engine, "before_cursor_execute", fail_second_audit)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
                {"business_date": "2026-11-01", "expected_version": 0},
                {"business_date": "2026-11-02", "expected_version": 0},
            ]})
            assert response.status_code == 500
    finally:
        event.remove(engine, "before_cursor_execute", fail_second_audit)
    with factory() as session:
        assert session.scalar(select(OperatingDay)) is None
        assert session.scalar(select(AuditEvent)) is None


def test_database_status_and_reason_checks(api):
    _app, factory = api
    for status, reason in (("Other", None), ("Closed", None), ("PlannedClosed", " "),
                           ("Open", "extra"), ("Closed", "x" * 501)):
        with pytest.raises(IntegrityError):
            with factory.begin() as session:
                session.add(OperatingDay(business_date=date(2026, 11, 1), status=status,
                                         closure_reason=reason, created_by_user_id=1,
                                         updated_by_user_id=1, version=1))


def test_date_lock_uses_distinct_transaction_scoped_namespace():
    class CaptureSession:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params=None):
            self.calls.append((str(statement), params))

    session = CaptureSession()
    lock_operating_date(session, date(2026, 11, 1))
    lock_operating_date(session, date(2026, 11, 1))
    lock_operating_date(session, date(2026, 11, 2))
    assert session.calls[0][0] == "SET LOCAL lock_timeout = '3s'"
    assert "pg_advisory_xact_lock" in session.calls[1][0]
    assert session.calls[1][1] == session.calls[3][1]
    assert session.calls[1][1] != session.calls[5][1]


def test_owner_gate_and_missing_session(api):
    app, _factory = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "cashier", "Cashier", "synthetic")
    with TestClient(app) as client:
        assert client.get("/api/v1/operating-days?from=2026-11-01&through=2026-11-01").status_code == 403
        assert put(client, "2026-11-01", "Open").status_code == 403
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
            {"business_date": "2026-11-01", "expected_version": 0}
        ]}).status_code == 403
        assert client.get("/api/v1/operating-days/2026-11-01/history").status_code == 403
    app.dependency_overrides.pop(get_current_principal)
    with TestClient(app) as client:
        assert client.get("/api/v1/operating-days?from=2026-11-01&through=2026-11-01").status_code == 401


def test_production_write_fence(api):
    app, factory = api
    app.dependency_overrides.pop(require_calendar_writes_ready)
    with TestClient(app) as client:
        assert put(client, "2026-11-01", "Open").status_code == 404
        assert client.post("/api/v1/operating-days/bulk-verify-open", json={"dates": [
            {"business_date": "2026-11-01", "expected_version": 0}
        ]}).status_code == 404
    with factory() as session:
        assert session.scalar(select(OperatingDay)) is None


def test_calendar_write_gate_is_explicit_and_local_only(monkeypatch):
    def target(host="localhost", database="yabs_salon_dev", sslmode=None):
        return URL.create("postgresql+psycopg", username="yabs_app", host=host,
                          database=database, query={"sslmode": sslmode} if sslmode else {})

    monkeypatch.setattr(feature, "get_database_url", lambda: target())
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.delenv("CALENDAR_WRITES_ENABLED", raising=False)
    with pytest.raises(ApiError) as disabled:
        require_calendar_writes_ready()
    assert disabled.value.status_code == 404

    monkeypatch.setenv("CALENDAR_WRITES_ENABLED", "1")
    require_calendar_writes_ready()
    for host, database, sslmode in (("db.neon.tech", "yabs_salon_dev", None),
                                    ("localhost", "yabs_salon_test", None),
                                    ("localhost", "yabs_salon_dev", "require")):
        monkeypatch.setattr(feature, "get_database_url",
                            lambda host=host, database=database, sslmode=sslmode:
                            target(host, database, sslmode))
        with pytest.raises(ApiError) as unsafe:
            require_calendar_writes_ready()
        assert unsafe.value.status_code == 404
    monkeypatch.setattr(feature, "get_database_url", lambda: target())
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ApiError) as production:
        require_calendar_writes_ready()
    assert production.value.status_code == 404


def test_origin_and_csrf_on_calendar_route(api, monkeypatch):
    app, _factory = api
    app.dependency_overrides.pop(get_current_principal)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://localhost")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "synthetic-testing-key-not-a-real-secret-123")
    monkeypatch.setattr(auth_dependencies, "validate_session", lambda _session, _token: SimpleNamespace(user_id=1, role="Owner"))
    token = "synthetic-session-token"
    with TestClient(app, base_url="http://localhost") as client:
        client.cookies.set("salon_session_dev", token)
        body = {"status": "Open", "closure_reason": None, "expected_version": 0}
        path = "/api/v1/operating-days/2026-11-01"
        assert client.put(path, json=body, headers={"X-CSRF-Token": csrf_token_for_session(token)}).status_code == 403
        assert client.put(path, json=body, headers={"Origin": "http://localhost"}).status_code == 403
        assert client.put(path, json=body, headers={"Origin": "http://localhost",
                                                    "X-CSRF-Token": csrf_token_for_session(token)}).status_code == 200
