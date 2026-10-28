"""HTTP contracts and coordinated default-off gate; no database connection."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import Response

from app.db.session import get_db_session
from app.main import app
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.transactions import attempt_router, router as sale_router
from app.modules.transactions.attempt_feature import attempt_protocol_enabled
from app.modules.transactions.schemas import SaleCreate, ManualSaleCreate


class FakeSession:
    def begin(self):
        class Transaction:
            def __enter__(self):
                return None

            def __exit__(self, *_args):
                return False

        return Transaction()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    attempt_protocol_enabled.cache_clear()
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "owner", "Owner", "synthetic")
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        attempt_protocol_enabled.cache_clear()


def enabled(monkeypatch):
    monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "1")
    attempt_protocol_enabled.cache_clear()


def direct():
    return {"source": "Direct", "sale": {"payment_method": "Cash", "items": [
        {"service_id": 1, "staff_id": 1, "selling_price": "100.00"},
    ]}}


def attempt(user_id=1, state="Reserved", source="Direct"):
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    return dict(id=4, user_id=user_id, idempotency_key=uuid4(), source=source,
                state=state, direct_reference="DS-000000000004" if source == "Direct" else None,
                manual_reference=None, transaction_id=8 if state == "Committed" else None,
                created_at=now, committed_at=now if state == "Committed" else None,
                cancelled_at=now if state == "Cancelled" else None)


def test_disabled_gate_and_no_store(api, monkeypatch):
    monkeypatch.setattr(attempt_router, "reserve_sale_attempt", lambda *_a, **_k: pytest.fail("disabled service called"))
    paths = ["/api/v1/sales/attempts", "/api/v1/sales/attempts/open",
             "/api/v1/sales/attempts/by-idempotency-key/" + str(uuid4()),
             "/api/v1/sales/attempts/4"]
    for path in paths:
        response = api.get(path)
        assert response.status_code == 404
        assert response.headers["Cache-Control"] == "no-store"
    response = api.post(paths[0], json=direct(), headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"
    response = api.post(paths[2] + "/cancel", json={"reason": "Verified", "evidence_verified": True})
    assert response.status_code == 404


def test_reservation_retry_and_strict_errors(api, monkeypatch):
    enabled(monkeypatch)
    result = attempt()
    calls = []

    def reserve(_session, payload, **kwargs):
        calls.append((payload.source, kwargs))
        return result, len(calls) > 1

    monkeypatch.setattr(attempt_router, "reserve_sale_attempt", reserve)
    key = str(result["idempotency_key"])
    first = api.post("/api/v1/sales/attempts", json=direct(), headers={"Idempotency-Key": key})
    assert first.status_code == 201, first.json()
    assert first.headers["Cache-Control"] == "no-store"
    assert "request_hash" not in first.json() and "gcash_reference" not in first.json()
    retry = api.post("/api/v1/sales/attempts", json=direct(), headers={"Idempotency-Key": key})
    assert retry.status_code == 200 and retry.json() == first.json()
    assert calls[0][1]["idempotency_key"] == result["idempotency_key"]
    assert calls[0][1]["actor_user_id"] == 1
    invalid = direct()
    invalid["sale"]["unknown"] = "x"
    assert api.post("/api/v1/sales/attempts", json=invalid,
                    headers={"Idempotency-Key": key}).status_code == 422
    assert api.post("/api/v1/sales/attempts", json=direct(),
                    headers={"Idempotency-Key": "bad"}).status_code == 422
    assert len(calls) == 2


def test_discovery_privacy_and_bounded_query(api, monkeypatch):
    enabled(monkeypatch)
    own = attempt(user_id=2)
    monkeypatch.setattr(attempt_router, "get_own_open_attempt", lambda *_a, **_k: own)
    monkeypatch.setattr(attempt_router, "get_attempt_detail", lambda *_a, **_k: own)
    seen = []

    def investigate(_session, *, role, query):
        seen.append((role, query))
        return [own]

    monkeypatch.setattr(attempt_router, "investigate_attempts", investigate)
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "cashier", "Cashier", "synthetic")
    open_response = api.get("/api/v1/sales/attempts/open")
    assert open_response.status_code == 200 and open_response.json()["user_id"] == 2
    detail = api.get("/api/v1/sales/attempts/4")
    assert detail.status_code == 200 and detail.headers["Cache-Control"] == "no-store"
    # The real service rejects cross-user detail with 404; list access is Owner-only.
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "owner", "Owner", "synthetic")
    listing = api.get("/api/v1/sales/attempts?recording_user_id=2&limit=2")
    assert listing.status_code == 200 and len(listing.json()) == 1
    assert seen[0][1].limit == 2 and seen[0][1].recording_user_id == 2
    assert api.get("/api/v1/sales/attempts?recording_user_id=2&limit=101").status_code == 422
    assert api.get("/api/v1/sales/attempts?recording_user_id=2&reference=invalid").status_code == 422
    assert api.get("/api/v1/sales/attempts?recording_user_id=2&created_from=2026-10-28T00:00:00Z&created_before=2026-10-27T00:00:00Z").status_code == 422
    assert len(seen) == 1


def test_exact_key_lookup_is_user_scoped_and_safe(api, monkeypatch):
    enabled(monkeypatch)
    key = uuid4()
    result = attempt(user_id=2, state="Cancelled")
    result["idempotency_key"] = key
    seen = []

    def lookup(_session, *, actor_user_id, role, idempotency_key):
        seen.append((actor_user_id, role, idempotency_key))
        return result

    monkeypatch.setattr(attempt_router, "get_own_attempt_by_key", lookup)
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "cashier", "Cashier", "synthetic")
    path = f"/api/v1/sales/attempts/by-idempotency-key/{key}"
    response = api.get(path)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert response.json()["state"] == "Cancelled"
    assert set(response.json()) == {
        "id", "user_id", "idempotency_key", "source", "state", "direct_reference",
        "manual_reference", "transaction_id", "created_at", "committed_at", "cancelled_at",
    }
    assert seen == [(2, "Cashier", key)]
    assert api.get("/api/v1/sales/attempts/by-idempotency-key/not-a-uuid").status_code == 422


def test_cancel_audit_contract_and_role(api, monkeypatch):
    enabled(monkeypatch)
    result = attempt(state="Cancelled")
    calls = []

    def cancel(_session, **kwargs):
        calls.append(kwargs)
        if kwargs["role"] == "Cashier":
            from app.core.exceptions import ApiError
            return None, ApiError(403, "forbidden", "Insufficient permissions")
        return result, None

    monkeypatch.setattr(attempt_router, "cancel_sale_attempt", cancel)
    path = "/api/v1/sales/attempts/4/cancel"
    body = {"reason": "Evidence checked", "evidence_verified": True}
    assert api.post(path, json={"reason": " ", "evidence_verified": True}).status_code == 422
    assert api.post(path, json={"reason": "Evidence checked", "evidence_verified": False}).status_code == 422
    assert not calls
    response = api.post(path, json=body)
    assert response.status_code == 200 and response.json()["state"] == "Cancelled"
    assert response.headers["Cache-Control"] == "no-store"
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "cashier", "Cashier", "synthetic")
    response = api.post(path, json=body)
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"
    assert calls[-1]["role"] == "Cashier"  # service records safe rejected audit


def test_origin_csrf_and_session_protection(api, monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "test-only-0123456789abcdef0123456789abcdef")
    app.dependency_overrides.pop(get_current_principal)
    path = "/api/v1/sales/attempts"
    response = api.get(path + "/open")
    assert response.status_code == 401
    assert api.get(path + "/by-idempotency-key/" + str(uuid4())).status_code == 401
    api.cookies.set("salon_session_dev", "synthetic-invalid-session")
    assert api.post(path, json=direct(), headers={"Idempotency-Key": str(uuid4())}).status_code == 403
    response = api.post(path, json=direct(), headers={
        "Idempotency-Key": str(uuid4()), "Origin": "http://localhost:5173",
    })
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_rejected"


def test_single_gate_controls_both_public_writers(api, monkeypatch):
    seen = []

    def direct_writer(_session, _payload, **kwargs):
        seen.append(("Direct", kwargs["enforce_reservation"]))
        return {"synthetic": True}, False

    def manual_writer(_session, _payload, **kwargs):
        seen.append(("Manual", kwargs["enforce_reservation"]))
        return {"synthetic": True}, False

    monkeypatch.setattr(sale_router, "record_direct_sale", direct_writer)
    monkeypatch.setattr(sale_router, "record_manual_sale", manual_writer)
    manual_payload = ManualSaleCreate.model_validate({
        "date_time": "2026-10-27T09:00:00+08:00", "manual_reference": "PAPER-20261027-001",
        "verified_against_paper": True, "payment_method": "Cash", "items": [{
            "service_id": 1, "staff_id": 1, "selling_price": "100.00",
            "item_name_snapshot": "Synthetic", "commission_type_snapshot": "Percentage",
            "commission_value_snapshot": "50.00",
        }],
    })
    for flag in (False, True):
        monkeypatch.setenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "1" if flag else "0")
        attempt_protocol_enabled.cache_clear()
        sale_router.post_direct_sale(SaleCreate.model_validate(direct()["sale"]), Response(),
                                     uuid4(), Principal(1, "owner", "Owner", "synthetic"), FakeSession())
        sale_router.post_manual_sale(manual_payload, Response(), uuid4(),
                                     Principal(1, "owner", "Owner", "synthetic"), FakeSession())
    assert seen == [("Direct", False), ("Manual", False), ("Direct", True), ("Manual", True)]
