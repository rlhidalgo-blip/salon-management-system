"""No database access: bounded-wait classification and inactive-route safety."""

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import ApiError
from app.modules.transactions.idempotency_lock import raise_retryable_sale_wait
from app.modules.transactions.router import post_direct_sale, post_manual_sale


class _PgError(Exception):
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate


@pytest.mark.parametrize("sqlstate", ["55P03", "57014", "40P01"])
def test_lock_timeout_and_deadlock_are_uncertain(sqlstate):
    error = DBAPIError("synthetic statement", {}, _PgError(sqlstate))
    with pytest.raises(ApiError) as caught:
        raise_retryable_sale_wait(error)
    assert caught.value.status_code == 503
    assert caught.value.code == "sale_outcome_uncertain"


def test_unrelated_database_errors_are_not_masked():
    error = DBAPIError("synthetic statement", {}, _PgError("23505"))
    with pytest.raises(DBAPIError):
        raise_retryable_sale_wait(error)


def test_public_sale_routes_do_not_activate_enforcement_yet():
    # Route signatures still call writers with their default development mode.
    assert "enforce_reservation" not in post_direct_sale.__code__.co_varnames
    assert "enforce_reservation" not in post_manual_sale.__code__.co_varnames
