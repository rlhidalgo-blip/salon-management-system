from decimal import Decimal

import pytest

from app.core.exceptions import ApiError
from app.modules.transactions.calculations import calculate_item
from app.modules.transactions.schemas import SaleCreate


@pytest.mark.parametrize("price,kind,value,commission,share", [
    ("100.50", "Percentage", "70.00", "70.00", "30.50"),
    ("100.50", "Percentage", "50.00", "50.00", "50.50"),
    ("101.00", "Percentage", "50.00", "51.00", "50.00"),
    ("100.25", "Fixed", "25.50", "26.00", "74.25"),
    ("100.25", None, None, "0.00", "100.25"),
])
def test_item_level_decimal_rounding(price, kind, value, commission, share):
    actual = calculate_item(Decimal(price), kind, Decimal(value) if value else None)
    assert actual == (Decimal(commission), Decimal(share))
    assert sum(actual) == Decimal(price)


@pytest.mark.parametrize("price,kind,value", [
    ("0.75", "Percentage", "100"),  # Whole-peso rounding would make share negative.
    ("10.50", "Fixed", "10.50"),
    ("10.00", "Fixed", "10.01"),
])
def test_overlarge_commission_is_rejected(price, kind, value):
    with pytest.raises(ApiError) as exc:
        calculate_item(Decimal(price), kind, Decimal(value))
    assert exc.value.status_code == 422


@pytest.mark.parametrize("payload", [
    {"payment_method": "Cash", "items": []},
    {"payment_method": "Cash", "gcash_reference": "x", "items": [{"service_id": 1, "staff_id": 1, "selling_price": "100"}]},
    {"payment_method": "GCash", "gcash_reference": " ", "items": [{"service_id": 1, "staff_id": 1, "selling_price": "100"}]},
    {"payment_method": "Cash", "items": [{"service_id": 1, "selling_price": "100"}]},
    {"payment_method": "Cash", "items": [{"product_id": 1, "selling_price": 100.0}]},
    {"payment_method": "Cash", "items": [{"product_id": 1, "selling_price": "1.001"}]},
    {"payment_method": "Cash", "items": [{"product_id": 1, "selling_price": "100", "quantity": 2}]},
])
def test_direct_sale_schema_rejects_invalid_input(payload):
    with pytest.raises(ValueError):
        SaleCreate.model_validate(payload)
