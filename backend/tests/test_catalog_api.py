"""Fast catalog API checks; PostgreSQL constraints and locks are tested separately."""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import install_error_handlers
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.catalog.models import Product, Service
from app.modules.catalog.router import router
from app.modules.commissions.models import CommissionRule


@pytest.fixture
def api():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (CommissionRule, Service, Product):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add_all([
            CommissionRule(id=1, name="Service", type="Percentage", value=Decimal("50")),
            CommissionRule(id=2, name="Product", type="Fixed", value=Decimal("25")),
            CommissionRule(id=3, name="Inactive", type="Fixed", value=Decimal("10"), active=False),
            CommissionRule(id=4, name="Alternate service", type="Percentage", value=Decimal("40")),
            CommissionRule(id=5, name="Alternate product", type="Fixed", value=Decimal("30")),
        ])
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_current_principal] = lambda: Principal(1, "synthetic", "Owner", "synthetic")
    try:
        with TestClient(app) as client:
            yield client, factory, app
    finally:
        engine.dispose()


def service_payload(**changes):
    return {"name": "Haircut", "current_price": "100.00", "allows_variable_price": False,
            "commission_rule_id": 1, **changes}


def product_payload(**changes):
    return {"name": "Shampoo", "current_price": "100.00", "commission_rule_id": 2, **changes}


def test_service_product_lifecycle_and_listing(api):
    client, factory, _app = api
    service = client.post("/api/v1/services", json=service_payload())
    product = client.post("/api/v1/products", json=product_payload())
    assert service.status_code == product.status_code == 201
    sid, pid = service.json()["id"], product.json()["id"]
    assert service.json()["active"] is product.json()["active"] is True
    assert service.json()["current_price"] == "100.00"
    assert client.patch(f"/api/v1/services/{sid}", json={"name": "  New haircut  ",
        "current_price": "120.50", "allows_variable_price": True}).json()["name"] == "New haircut"
    assert client.patch(f"/api/v1/services/{sid}", json={"commission_rule_id": 4}).json()["commission_rule_id"] == 4
    assert client.patch(f"/api/v1/products/{pid}", json={"current_price": "30.00"}).status_code == 200
    assert client.patch(f"/api/v1/products/{pid}", json={"commission_rule_id": 5}).json()["commission_rule_id"] == 5
    assert client.patch(f"/api/v1/services/{sid}/status", json={"active": False}).json()["active"] is False
    assert client.patch(f"/api/v1/services/{sid}/status", json={"active": True}).json()["active"] is True
    assert client.patch(f"/api/v1/products/{pid}/status", json={"active": False}).json()["active"] is False
    assert client.patch(f"/api/v1/products/{pid}/status", json={"active": True}).json()["active"] is True
    assert [row["id"] for row in client.get("/api/v1/services").json()] == [sid]
    assert [row["id"] for row in client.get("/api/v1/products").json()] == [pid]
    assert client.delete(f"/api/v1/products/{pid}").status_code == 405
    with factory() as session:
        assert session.scalar(select(Service).where(Service.id == sid)).current_price == Decimal("120.50")


@pytest.mark.parametrize("path,payload", [
    ("services", service_payload(name=" ")),
    ("services", service_payload(current_price="0")),
    ("services", service_payload(current_price="1.001")),
    ("services", service_payload(allows_variable_price="yes")),
    ("services", service_payload(commission_rule_id=2)),
    ("services", service_payload(commission_rule_id=999)),
    ("services", service_payload(unapproved=True)),
    ("products", product_payload(name=" ")),
    ("products", product_payload(current_price="-1")),
    ("products", product_payload(current_price="1.001")),
    ("products", product_payload(commission_rule_id=1)),
    ("products", product_payload(commission_rule_id=3)),
    ("products", product_payload(current_price="24.99")),
    ("products", product_payload(unapproved=True)),
])
def test_creation_rejects_invalid_values_without_writes(api, path, payload):
    client, factory, _app = api
    response = client.post(f"/api/v1/{path}", json=payload)
    assert response.status_code in (404, 409, 422)
    assert set(response.json()["error"]) == {"code", "message", "details", "request_id"}
    with factory() as session:
        assert session.query(Service if path == "services" else Product).count() == 0


def test_assignment_price_status_and_inactive_rule(api):
    client, factory, _app = api
    product_id = client.post("/api/v1/products", json=product_payload()).json()["id"]
    path = f"/api/v1/products/{product_id}"
    assert client.patch(path, json={"current_price": "24.99"}).status_code == 422
    assert client.patch(path, json={"commission_rule_id": 1}).status_code == 422
    assert client.patch(path, json={"commission_rule_id": 3}).status_code == 409
    assert client.patch(path, json={"name": None}).status_code == 422
    assert client.patch(path, json={}).status_code == 422
    assert client.patch(path, json={"active": False}).status_code == 422
    assert client.patch(path + "/status", json={"active": "false"}).status_code == 422
    assert client.patch(path + "/status", json={"active": False}).status_code == 200
    with factory.begin() as session:
        session.get(Product, product_id).commission_rule_id = 3  # Existing inactive reference; not a new API assignment.
    assert client.patch(path, json={"name": "Other"}).status_code == 200
    assert client.patch(path + "/status", json={"active": True}).status_code == 409
    assert client.patch(path, json={"commission_rule_id": 2}).status_code == 200
    assert client.patch(path + "/status", json={"active": True}).status_code == 200


def test_owner_only(api):
    client, _factory, app = api
    app.dependency_overrides[get_current_principal] = lambda: Principal(2, "cashier", "Cashier", "synthetic")
    assert client.get("/api/v1/services").status_code == 403
    assert client.get("/api/v1/products").status_code == 403
    assert client.post("/api/v1/services", json=service_payload()).status_code == 403
    assert client.patch("/api/v1/products/1/status", json={"active": False}).status_code == 403
    del app.dependency_overrides[get_current_principal]
    assert client.get("/api/v1/services").status_code == 401
