"""Explicitly opted-in, REAL-COMMIT sale tests on local yabs_salon_test only.

These tests cannot guarantee cleanup after process, machine, or database failure.
Never run them against development/production, or alongside other DB writers.
"""

import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from decimal import Decimal
from ipaddress import ip_address
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.security import hash_password
from app.db.session import get_db_session
from app.main import app
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.catalog.models import Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.idempotency_models import SaleIdempotency
from app.modules.transactions.models import Transaction, TransactionItem
from app.modules.users.models import User


ORIGIN = "http://localhost"
REVISION = "20261020_01"
PREFIX = "synthetic-durable-sale-"


def _target_is_safe(connection, url) -> None:
    """Check configured and actual target before every committed write/cleanup."""
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured database target")
    if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
        raise RuntimeError("Unsafe connected database")
    if connection.scalar(text("SELECT current_user")) != "yabs_app":
        raise RuntimeError("Unsafe connected user")
    server_address = connection.scalar(text("SELECT inet_server_addr()"))
    if server_address is None or not ip_address(str(server_address)).is_loopback:
        raise RuntimeError("Database server is not on loopback")
    if connection.scalar(text("SELECT current_schema()")) != "public":
        raise RuntimeError("Unexpected database schema")
    if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
        raise RuntimeError("Missing Alembic revision table")
    if (connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1
            or connection.scalar(text("SELECT version_num FROM public.alembic_version")) != REVISION):
        raise RuntimeError("Unexpected Alembic revision")


@dataclass
class Case:
    engine: object
    url: object
    marker: str
    owner_user_id: int | None = None
    catalog_user_id: int | None = None
    ids: dict[str, set] = field(default_factory=lambda: {name: set() for name in (
        "users", "staff", "commission_rules", "services", "auth_sessions", "audit_events",
        "transactions", "transaction_items", "sale_idempotency",
    )})
    clients: tuple[TestClient, TestClient, TestClient] | None = None
    headers: tuple[dict[str, str], dict[str, str], dict[str, str]] | None = None

    @property
    def user_id(self):
        return self.owner_user_id

    @property
    def service_id(self):
        return next(iter(self.ids["services"]))

    @property
    def rule_id(self):
        return next(iter(self.ids["commission_rules"]))

    @property
    def staff_id(self):
        return next(iter(self.ids["staff"]))

    def payload(self, price="101.00"):
        return {"payment_method": "Cash", "items": [
            {"service_id": self.service_id, "staff_id": self.staff_id, "selling_price": price},
        ]}

    def post(self, client_index: int, payload: dict, key: str):
        headers = {**self.headers[client_index], "Idempotency-Key": key}
        return self.clients[client_index].post("/api/v1/transactions", json=payload, headers=headers)


def _track_owned_rows(case: Case, connection) -> None:
    """Identify rows by the unique synthetic user, never by broad table scans."""
    if not case.ids["users"]:
        return
    for user_id, expected_username in (
        (case.owner_user_id, case.marker + "-owner"),
        (case.catalog_user_id, case.marker + "-catalog-owner"),
    ):
        username = connection.scalar(select(User.username).where(User.id == user_id))
        if username != expected_username:
            raise RuntimeError("Synthetic user ownership mismatch")
        for name, model, fk in (
            ("auth_sessions", AuthSession, AuthSession.user_id),
            ("audit_events", AuditEvent, AuditEvent.actor_user_id),
            ("sale_idempotency", SaleIdempotency, SaleIdempotency.user_id),
            ("transactions", Transaction, Transaction.recorded_by_user_id),
        ):
            case.ids[name].update(connection.scalars(select(model.id).where(fk == user_id)))
    sale_ids = case.ids["transactions"]
    claims = set(connection.scalars(select(SaleIdempotency.transaction_id).where(
        SaleIdempotency.user_id.in_(case.ids["users"]), SaleIdempotency.transaction_id.is_not(None))))
    if sale_ids != claims:
        raise RuntimeError("Synthetic sale/claim mismatch; refuse automatic deletion")
    if sale_ids:
        case.ids["transaction_items"].update(connection.scalars(select(TransactionItem.id).where(
            TransactionItem.transaction_id.in_(sale_ids))))


def _cleanup(case: Case) -> None:
    """Delete only identified synthetic rows, then verify using a fresh connection."""
    try:
        with case.engine.begin() as connection:
            _target_is_safe(connection, case.url)
            _track_owned_rows(case, connection)
            for name, model, expected_name in (
                ("services", Service, case.marker + "-service"),
                ("staff", Staff, case.marker + "-staff"),
                ("commission_rules", CommissionRule, case.marker + "-rule"),
            ):
                for row_id in case.ids[name]:
                    actual = connection.scalar(select(model.name).where(model.id == row_id))
                    if actual is not None and not actual.startswith(expected_name):
                        raise RuntimeError("Synthetic ownership mismatch")
            if case.ids["users"]:
                if (connection.scalar(select(User.username).where(User.id == case.owner_user_id)) != case.marker + "-owner"
                        or connection.scalar(select(User.username).where(User.id == case.catalog_user_id))
                        != case.marker + "-catalog-owner"):
                    raise RuntimeError("Synthetic user ownership mismatch")
            for name, model in (
                ("transaction_items", TransactionItem),
                ("sale_idempotency", SaleIdempotency),
                ("transactions", Transaction),
                ("auth_sessions", AuthSession),
                ("audit_events", AuditEvent),
                ("services", Service),
                ("staff", Staff),
                ("commission_rules", CommissionRule),
                ("users", User),
            ):
                if case.ids[name]:
                    connection.execute(delete(model).where(model.id.in_(case.ids[name])))
        with case.engine.connect() as verifier:
            _target_is_safe(verifier, case.url)
            for name, model in (
                ("transaction_items", TransactionItem),
                ("sale_idempotency", SaleIdempotency),
                ("transactions", Transaction),
                ("auth_sessions", AuthSession),
                ("audit_events", AuditEvent),
                ("services", Service),
                ("staff", Staff),
                ("commission_rules", CommissionRule),
                ("users", User),
            ):
                if case.ids[name]:
                    if verifier.scalar(select(func.count()).select_from(model).where(
                            model.id.in_(case.ids[name]))) != 0:
                        raise RuntimeError("Synthetic rows remain after cleanup")
    except Exception as exc:
        raise AssertionError(f"Synthetic cleanup/verification failed: run={case.marker}, ids={case.ids}") from exc


@pytest.fixture
def durable_case(monkeypatch):
    # Skip BEFORE reading .env or opening any connection on ordinary pytest.
    if os.getenv("RUN_SALES_DURABILITY_TESTS") != "1":
        pytest.skip("Set RUN_SALES_DURABILITY_TESTS=1 for real-commit yabs_salon_test tests")
    url = get_database_url()
    if url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test" or url.host not in (
        "localhost", "127.0.0.1", "::1") or url.username != "yabs_app":
        pytest.fail("Unsafe configured database target; no writes attempted")
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=2,
                           connect_args={"connect_timeout": 5,
                                         "options": "-c statement_timeout=15000 -c lock_timeout=12000"})
    case = Case(engine=engine, url=url, marker=PREFIX + uuid4().hex)
    override_installed = False
    setup_committed = False
    try:
        with engine.connect() as connection:
            _target_is_safe(connection, url)
            # A previous interrupted durable run requires human review; never
            # delete it as part of a new test run.
            if connection.scalar(select(func.count()).select_from(User).where(
                User.username.like(PREFIX + "%"))):
                pytest.fail("Previous synthetic durable user exists; no writes attempted")
        monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
        monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", ORIGIN)
        monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", secrets.token_urlsafe(32))
        password = secrets.token_urlsafe(32)
        with engine.begin() as connection:
            _target_is_safe(connection, url)
            case.owner_user_id = connection.execute(insert(User).values(
                username=case.marker + "-owner", password_hash=hash_password(password),
                role="Owner", active=True,
            ).returning(User.id)).scalar_one()
            case.ids["users"].add(case.owner_user_id)
            case.catalog_user_id = connection.execute(insert(User).values(
                username=case.marker + "-catalog-owner", password_hash=hash_password(password),
                role="Owner", active=True,
            ).returning(User.id)).scalar_one()
            case.ids["users"].add(case.catalog_user_id)
            case.ids["staff"].add(connection.execute(insert(Staff).values(
                name=case.marker + "-staff", role="Stylist", active=True,
            ).returning(Staff.id)).scalar_one())
            case.ids["commission_rules"].add(connection.execute(insert(CommissionRule).values(
                name=case.marker + "-rule", type="Percentage", value=Decimal("50.00"), active=True,
            ).returning(CommissionRule.id)).scalar_one())
            case.ids["services"].add(connection.execute(insert(Service).values(
                name=case.marker + "-service", current_price=Decimal("101.00"),
                commission_rule_id=case.rule_id, active=True,
            ).returning(Service.id)).scalar_one())
        setup_committed = True

        def session_override():
            # No outer transaction and no join_transaction_mode: route commits
            # really persist and separate requests use distinct pooled connections.
            with Session(bind=engine, autoflush=False, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_db_session] = session_override
        override_installed = True
        with ExitStack() as stack:
            first = stack.enter_context(TestClient(app, base_url=ORIGIN))
            second = stack.enter_context(TestClient(app, base_url=ORIGIN))
            third = stack.enter_context(TestClient(app, base_url=ORIGIN))
            case.clients = (first, second, third)
            headers = []
            for index, client in enumerate(case.clients):
                login = client.post("/api/v1/auth/login", json={
                    "username": case.marker + ("-owner" if index < 2 else "-catalog-owner"),
                    "password": password,
                }, headers={"Origin": ORIGIN})
                assert login.status_code == 200
                headers.append({"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]})
            case.headers = tuple(headers)
            yield case
    finally:
        if override_installed:
            app.dependency_overrides.pop(get_db_session, None)
        try:
            if setup_committed:
                _cleanup(case)
        finally:
            engine.dispose()


def test_durable_visibility_replay_conflict_and_failure(durable_case: Case):
    case = durable_case
    key = str(uuid4())
    payload = case.payload()
    first = case.post(0, payload, key)
    assert first.status_code == 201, first.json()
    sale_id = first.json()["id"]
    case.ids["transactions"].add(sale_id)
    with case.engine.connect() as independent:
        _target_is_safe(independent, case.url)
        assert independent.scalar(select(Transaction.id).where(Transaction.id == sale_id)) == sale_id
        assert independent.scalar(select(func.count()).select_from(TransactionItem).where(
            TransactionItem.transaction_id == sale_id)) == 1
        assert independent.scalar(select(SaleIdempotency.transaction_id).where(
            SaleIdempotency.user_id == case.user_id, SaleIdempotency.idempotency_key == key)) == sale_id
    replay = case.post(1, payload, key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert case.post(1, {**payload, "payment_method": "GCash", "gcash_reference": "synthetic"}, key).status_code == 409
    failed_key = str(uuid4())
    invalid = {"payment_method": "Cash", "items": [
        payload["items"][0], {**payload["items"][0], "selling_price": "100.00"},
    ]}
    assert case.post(0, invalid, failed_key).status_code == 422
    with case.engine.connect() as independent:
        _target_is_safe(independent, case.url)
        assert independent.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.user_id, SaleIdempotency.idempotency_key == failed_key)) == 0
        assert independent.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.user_id)) == 1
        assert independent.scalar(select(func.count()).select_from(TransactionItem).where(
            TransactionItem.transaction_id == sale_id)) == 1


def test_two_connections_same_key_create_one_sale(durable_case: Case, monkeypatch):
    case = durable_case
    import app.modules.transactions.router as sale_router

    original = sale_router.record_direct_sale
    gate = threading.Barrier(2)
    pids = set()
    guard = threading.Lock()

    def coordinated(session, payload, *, actor_user_id, idempotency_key):
        pid = session.scalar(text("SELECT pg_backend_pid()"))
        with guard:
            pids.add(pid)
        gate.wait(timeout=10)
        return original(session, payload, actor_user_id=actor_user_id, idempotency_key=idempotency_key)

    monkeypatch.setattr(sale_router, "record_direct_sale", coordinated)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(case.post, index, case.payload(), key) for index in (0, 1)]
        responses = [future.result(timeout=25) for future in futures]
    assert len(pids) == 2, "Requests did not use separate PostgreSQL connections"
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    sale_id = responses[0].json()["id"]
    case.ids["transactions"].add(sale_id)
    with case.engine.connect() as independent:
        _target_is_safe(independent, case.url)
        assert independent.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.recorded_by_user_id == case.user_id)) == 1
        assert independent.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.user_id)) == 1
        assert independent.scalar(select(func.count()).select_from(TransactionItem).where(
            TransactionItem.transaction_id == sale_id)) == 1


def test_catalog_update_waits_for_sale_and_preserves_snapshot(durable_case: Case, monkeypatch):
    case = durable_case
    import app.modules.catalog.router as catalog_router
    import app.modules.transactions.service as sale_service

    entered_sale = threading.Event()
    release_sale = threading.Event()
    update_started = threading.Event()
    update_pid = []
    original_calculate = sale_service.calculate_item
    original_change = catalog_router.change_item

    def paused_calculate(*args, **kwargs):
        # This is reached after the sale locked rule + catalog rows and flushed
        # its header. Only test code pauses; production service remains intact.
        entered_sale.set()
        assert release_sale.wait(timeout=10), "Timed out waiting to release sale"
        return original_calculate(*args, **kwargs)

    def tracked_change(session, *args, **kwargs):
        update_pid.append(session.scalar(text("SELECT pg_backend_pid()")))
        update_started.set()
        return original_change(session, *args, **kwargs)

    monkeypatch.setattr(sale_service, "calculate_item", paused_calculate)
    monkeypatch.setattr(catalog_router, "change_item", tracked_change)
    key = str(uuid4())
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            sale_future = pool.submit(case.post, 0, case.payload(), key)
            assert entered_sale.wait(timeout=10), "Sale never reached locked calculation"
            # Separate Owner avoids authentication's user-row lock masking the
            # catalog/rule-lock behavior under test.
            update_future = pool.submit(case.clients[2].patch, f"/api/v1/services/{case.service_id}",
                                        json={"name": case.marker + "-service-updated", "current_price": "120.00"},
                                        headers=case.headers[2])
            assert update_started.wait(timeout=10), "Catalog update never started"
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline:
                with case.engine.connect() as observer:
                    _target_is_safe(observer, case.url)
                    blocked = observer.scalar(text(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"
                    ), {"pid": update_pid[0]}) is True
                if blocked:
                    break
                time.sleep(0.05)
            assert blocked, "Catalog write did not wait for the sale's row lock"
            release_sale.set()
            sale = sale_future.result(timeout=25)
            update = update_future.result(timeout=25)
    finally:
        release_sale.set()
    assert sale.status_code == 201, sale.json()
    assert update.status_code == 200, update.json()
    item = sale.json()["items"][0]
    assert item["item_name_snapshot"] == case.marker + "-service"
    assert item["selling_price"] == "101.00"
    assert item["commission_value_snapshot"] == "50.00"
    assert item["staff_commission"] == "51.00"
    case.ids["transactions"].add(sale.json()["id"])
    with case.engine.connect() as independent:
        _target_is_safe(independent, case.url)
        assert independent.scalar(select(Service.name).where(Service.id == case.service_id)) == case.marker + "-service-updated"
        assert independent.scalar(select(TransactionItem.item_name_snapshot).where(
            TransactionItem.transaction_id == sale.json()["id"])) == case.marker + "-service"


def test_sales_options_and_user_scoped_lookup(durable_case: Case):
    case = durable_case
    options = case.clients[0].get("/api/v1/sales/options")
    assert options.status_code == 200
    assert options.headers["cache-control"] == "no-store"
    assert any(row["id"] == case.staff_id for row in options.json()["staff"])
    assert any(row["id"] == case.service_id for row in options.json()["services"])
    assert "commission_rule_id" not in str(options.json())
    assert case.clients[1].get("/api/v1/sales/options").status_code == 200
    key = str(uuid4())
    url = f"/api/v1/transactions/by-idempotency-key/{key}"
    absent = case.clients[0].get(url)
    assert absent.status_code == 200
    assert absent.json() == {"status": "not_committed_at_check", "sale": None}
    sale = case.post(0, case.payload(), key)
    assert sale.status_code == 201, sale.json()
    case.ids["transactions"].add(sale.json()["id"])
    committed = case.clients[1].get(url)
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    assert committed.json()["sale"] == sale.json()
    assert case.clients[2].get(url).json() == {"status": "not_committed_at_check", "sale": None}
    assert case.clients[0].get("/api/v1/transactions/by-idempotency-key/nope").status_code == 422
    assert TestClient(app, base_url=ORIGIN).get(url).status_code == 401
    assert case.post(1, case.payload(), key).status_code == 200
    with case.engine.connect() as independent:
        _target_is_safe(independent, case.url)
        assert independent.scalar(select(func.count()).select_from(SaleIdempotency).where(
            SaleIdempotency.user_id == case.user_id, SaleIdempotency.idempotency_key == key)) == 1


def test_processing_lookup_and_delayed_post(durable_case: Case, monkeypatch):
    case = durable_case
    import app.modules.transactions.service as sale_service

    entered = threading.Event()
    release = threading.Event()
    original_lock = sale_service.lock_sale_key

    def paused_lock(session, user_id, key):
        original_lock(session, user_id, key)
        entered.set()
        assert release.wait(timeout=10), "Timed out waiting to release advisory lock"

    monkeypatch.setattr(sale_service, "lock_sale_key", paused_lock)
    key = str(uuid4())
    url = f"/api/v1/transactions/by-idempotency-key/{key}"
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(case.post, 0, case.payload(), key)
            assert entered.wait(timeout=10)
            processing = case.clients[1].get(url)
            assert processing.status_code == 202, processing.json()
            assert processing.json() == {"status": "processing", "sale": None}
            release.set()
            sale = pending.result(timeout=25)
    finally:
        release.set()
    assert sale.status_code == 201, sale.json()
    case.ids["transactions"].add(sale.json()["id"])
    assert case.clients[1].get(url).json()["status"] == "committed"

    # Absence at a check does not prevent a delayed original POST from committing.
    delayed_key = str(uuid4())
    delayed_url = f"/api/v1/transactions/by-idempotency-key/{delayed_key}"
    assert case.clients[1].get(delayed_url).json()["status"] == "not_committed_at_check"
    delayed = case.post(0, case.payload(), delayed_key)
    assert delayed.status_code == 201, delayed.json()
    case.ids["transactions"].add(delayed.json()["id"])
    assert case.post(1, case.payload(), delayed_key).status_code == 200
    assert case.clients[1].get(delayed_url).json()["sale"]["id"] == delayed.json()["id"]
