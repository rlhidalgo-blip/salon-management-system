"""Opt-in HTTP integration; temporary migration and every synthetic row roll back."""

import os
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.db.session import get_db_session
from app.main import app
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.transactions.attempt_feature import attempt_protocol_enabled


REVISION = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))).get_revision("20261027_01").module


def preflight(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        raise RuntimeError("Unsafe configured test target")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if (address is None or not ip_address(str(address)).is_loopback
            or connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"
            or connection.scalar(text("SELECT count(*) FROM public.alembic_version")) != 1):
        raise RuntimeError("Unsafe connected target or revision")
    revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
    exists = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
    if (revision, exists) not in (("20261020_01", False), ("20261027_01", True)):
        raise RuntimeError("Unexpected schema revision or sale_attempts state")
    return exists


def test_attempt_api_real_services_rollback_only(monkeypatch):
    if os.getenv("RUN_SALE_ATTEMPT_API_TESTS") != "1":
        pytest.skip("Set RUN_SALE_ATTEMPT_API_TESTS=1 for rollback-only yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured test target; no connection attempted")
    engine = sa.create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-c1-" + uuid4().hex
    try:
        with engine.connect() as connection:
            migrated = preflight(connection, url)
            before = tuple(connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in
                           ("users", "transactions", "sale_idempotency", "audit_events"))
            scope = connection.begin_nested()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '3s'"))
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                if not migrated:
                    with Operations.context(MigrationContext.configure(connection)):
                        REVISION.upgrade()
                owner_id = connection.scalar(text(
                    "INSERT INTO users (username,password_hash,role) "
                    "VALUES (:name,'synthetic-unused','Owner') RETURNING id"
                ), {"name": marker + "-owner"})
                cashier_id = connection.scalar(text(
                    "INSERT INTO users (username,password_hash,role) "
                    "VALUES (:name,'synthetic-unused','Cashier') RETURNING id"
                ), {"name": marker + "-cashier"})
                principal = {"value": Principal(cashier_id, marker + "-cashier", "Cashier", "synthetic")}

                def session_override():
                    with Session(bind=connection, autoflush=False, expire_on_commit=False,
                                 join_transaction_mode="create_savepoint") as session:
                        yield session

                monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "1")
                attempt_protocol_enabled.cache_clear()
                app.dependency_overrides[get_db_session] = session_override
                app.dependency_overrides[get_current_principal] = lambda: principal["value"]
                try:
                    with TestClient(app) as client:
                        key = uuid4()
                        body = {"source": "Direct", "sale": {"payment_method": "Cash", "items": [
                            {"service_id": 1, "staff_id": 1, "selling_price": "100.00"},
                        ]}}
                        path = "/api/v1/sales/attempts"
                        first = client.post(path, json=body, headers={"Idempotency-Key": str(key)})
                        assert first.status_code == 201, first.json()
                        attempt = first.json()
                        assert attempt["direct_reference"] == f"DS-{attempt['id']:012d}"
                        assert "request_hash" not in attempt and "gcash_reference" not in attempt
                        assert first.headers["Cache-Control"] == "no-store"
                        retry = client.post(path, json=body, headers={"Idempotency-Key": str(key)})
                        assert retry.status_code == 200 and retry.json() == attempt
                        assert client.get(path + "/open").json()["id"] == attempt["id"]
                        assert client.get(path + f"/{attempt['id']}").json()["id"] == attempt["id"]
                        key_path = path + f"/by-idempotency-key/{key}"
                        own_key = client.get(key_path)
                        assert own_key.status_code == 200 and own_key.json() == attempt
                        assert own_key.headers["Cache-Control"] == "no-store"
                        assert client.get(path, params={"recording_user_id": cashier_id}).status_code == 403
                        denied = client.post(path + f"/{attempt['id']}/cancel", json={
                            "reason": "Synthetic denial", "evidence_verified": True,
                        })
                        assert denied.status_code == 403
                        assert client.get(path + "/open").json()["state"] == "Reserved"
                        unreserved = client.post("/api/v1/transactions", json=body["sale"], headers={
                            "Idempotency-Key": str(uuid4()),
                        })
                        assert unreserved.status_code == 409
                        assert unreserved.json()["error"]["code"] == "reservation_required"
                        occurred = connection.scalar(text("SELECT clock_timestamp()"))
                        paper = "PAPER-" + occurred.astimezone(ZoneInfo("Asia/Manila")).strftime("%Y%m%d") + "-001"
                        manual_body = {
                            "date_time": occurred.isoformat(), "manual_reference": paper,
                            "verified_against_paper": True, "payment_method": "Cash", "items": [{
                                "service_id": 1, "staff_id": 1, "selling_price": "100.00",
                                "item_name_snapshot": "Synthetic historical item",
                                "commission_type_snapshot": "Percentage",
                                "commission_value_snapshot": "50.00",
                            }],
                        }
                        unreserved_manual = client.post("/api/v1/transactions/manual", json=manual_body,
                                                        headers={"Idempotency-Key": str(uuid4())})
                        assert unreserved_manual.status_code == 409
                        assert unreserved_manual.json()["error"]["code"] == "reservation_required"
                        principal["value"] = Principal(owner_id, marker + "-owner", "Owner", "synthetic")
                        owner_key = uuid4()
                        owner_attempt = client.post(path, json=body, headers={"Idempotency-Key": str(owner_key)})
                        assert owner_attempt.status_code == 201, owner_attempt.json()
                        principal["value"] = Principal(cashier_id, marker + "-cashier", "Cashier", "synthetic")
                        assert client.get(path + f"/{owner_attempt.json()['id']}").status_code == 404
                        missing = client.get(path + f"/by-idempotency-key/{uuid4()}")
                        other_user = client.get(path + f"/by-idempotency-key/{owner_key}")
                        assert missing.status_code == other_user.status_code == 404
                        for response in (missing, other_user):
                            assert response.json()["error"]["code"] == "not_found"
                            assert response.json()["error"]["message"] == "Sale attempt not found"
                        principal["value"] = Principal(owner_id, marker + "-owner", "Owner", "synthetic")
                        found = client.get(path, params={"recording_user_id": cashier_id,
                                                         "reference": attempt["direct_reference"]})
                        assert found.status_code == 200 and [row["id"] for row in found.json()] == [attempt["id"]]
                        cancelled = client.post(path + f"/{attempt['id']}/cancel", json={
                            "reason": "Synthetic external evidence verified", "evidence_verified": True,
                        })
                        assert cancelled.status_code == 200 and cancelled.json()["state"] == "Cancelled"
                        assert client.post(path + f"/{attempt['id']}/cancel", json={
                            "reason": "Synthetic external evidence verified", "evidence_verified": True,
                        }).status_code == 409
                        principal["value"] = Principal(cashier_id, marker + "-cashier", "Cashier", "synthetic")
                        assert client.get(path + "/open").json() is None
                        assert client.get(key_path).json()["state"] == "Cancelled"
                        assert client.post(path, json=body, headers={"Idempotency-Key": str(key)}).status_code == 409
                        assert connection.scalar(text("SELECT count(*) FROM audit_events "
                                                      "WHERE resource_type='sale_attempt' AND resource_id=:id"),
                                                 {"id": str(attempt["id"])}) == 3
                finally:
                    app.dependency_overrides.clear()
                    attempt_protocol_enabled.cache_clear()
            finally:
                scope.rollback()
                connection.rollback()
        with engine.connect() as verifier:
            preflight(verifier, url)
            assert tuple(verifier.scalar(text(f"SELECT count(*) FROM {table}")) for table in
                         ("users", "transactions", "sale_idempotency", "audit_events")) == before
            assert verifier.scalar(text("SELECT count(*) FROM users WHERE username LIKE :prefix"),
                                   {"prefix": marker + "%"}) == 0
    finally:
        engine.dispose()
