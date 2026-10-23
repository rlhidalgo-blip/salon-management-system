"""Per-unit financial snapshots; all arithmetic stays in Decimal."""

from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import ApiError


CENT = Decimal("0.01")
PESO = Decimal("1")
ZERO = Decimal("0.00")


def calculate_item(selling_price: Decimal, commission_type: str | None,
                   commission_value: Decimal | None) -> tuple[Decimal, Decimal]:
    if selling_price <= 0 or selling_price != selling_price.quantize(CENT):
        raise ApiError(422, "invalid_price", "Selling price must be positive with at most two decimal places")
    if commission_type is None and commission_value is None:
        return ZERO, selling_price
    if commission_type == "Percentage" and commission_value is not None and 0 < commission_value <= 100:
        raw = selling_price * commission_value / Decimal("100")
    elif commission_type == "Fixed" and commission_value is not None and commission_value > 0:
        raw = commission_value
    else:
        raise ApiError(422, "invalid_commission", "Invalid commission rule")
    if commission_type == "Fixed" and raw > selling_price:
        raise ApiError(422, "commission_exceeds_price", "Fixed commission exceeds selling price")
    commission = raw.quantize(PESO, rounding=ROUND_HALF_UP).quantize(CENT)
    if commission > selling_price:
        raise ApiError(422, "commission_exceeds_price", "Rounded commission exceeds selling price")
    share = selling_price - commission
    return commission, share
