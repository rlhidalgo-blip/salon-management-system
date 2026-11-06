"""Opt-in, read-only lock contention on the isolated local PostgreSQL test DB."""

import os
from datetime import date
from ipaddress import ip_address

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.core.exceptions import ApiError
from app.modules.operating_days.date_lock import lock_operating_date


def _safe_target(connection, url):
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe PostgreSQL target; no lock attempted")
    if (connection.scalar(text("SELECT current_database()")) != "yabs_salon_test"
            or connection.scalar(text("SELECT current_user")) != "yabs_app"
            or connection.scalar(text("SELECT current_schema()")) != "public"):
        pytest.fail("Unexpected PostgreSQL identity; no lock attempted")
    address = connection.scalar(text("SELECT inet_server_addr()"))
    if address is None or not ip_address(str(address)).is_loopback:
        pytest.fail("PostgreSQL is not loopback; no lock attempted")
    if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
        pytest.fail("Missing Alembic revision; no lock attempted")
    if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261104_01":
        pytest.fail("Unexpected Alembic revision; no lock attempted")


def test_same_date_lock_contention_and_transaction_release():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for isolated yabs_salon_test checks")
    url = get_database_url()
    if (url.drivername != "postgresql+psycopg" or url.database != "yabs_salon_test"
            or url.host not in ("localhost", "127.0.0.1", "::1") or url.username != "yabs_app"):
        pytest.fail("Unsafe configured PostgreSQL target; no connection attempted")
    engine = create_engine(url, connect_args={"connect_timeout": 5}, pool_size=2, max_overflow=0)
    try:
        with engine.connect() as connection:
            _safe_target(connection, url)
        day = date(2026, 11, 1)
        with Session(engine) as first, Session(engine) as second:
            lock_operating_date(first, day)
            with pytest.raises(ApiError) as error:
                lock_operating_date(second, day)
            assert (error.value.status_code, error.value.code) == (503, "calendar_busy")
            second.rollback()
            with pytest.raises(ApiError) as sale_error:
                lock_operating_date(second, day, for_sale=True)
            assert (sale_error.value.status_code, sale_error.value.code) == (503, "sale_outcome_uncertain")
            second.rollback()
            first.rollback()
            lock_operating_date(second, day)
            second.rollback()
    finally:
        engine.dispose()
