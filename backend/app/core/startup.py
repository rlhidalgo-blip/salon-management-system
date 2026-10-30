"""Fail closed before serving production or reservation-aware traffic."""

import os

from sqlalchemy import text

from app.core.config import get_auth_api_config, get_auth_config, get_database_url
from app.db.session import get_engine
from app.modules.transactions.attempt_feature import attempt_protocol_enabled


EXPECTED_REVISION = "20261027_01"


def validate_startup_configuration() -> None:
    # Reading auth configuration first also loads backend/.env for the process-stable gate.
    cookie = get_auth_config()
    environment = os.getenv("APP_ENV", "development")
    if environment not in ("development", "production"):
        raise RuntimeError("APP_ENV must be development or production")
    production = environment == "production"
    if production:
        auth = get_auth_api_config()
        if (not cookie.cookie_secure or cookie.cookie_name != "__Host-salon_session"
                or not cookie.cookie_httponly or cookie.cookie_samesite != "lax"
                or cookie.cookie_path != "/" or cookie.cookie_domain is not None
                or not auth.allowed_origin.startswith("https://")):
            raise RuntimeError("Production authentication configuration is invalid")

    reserved = attempt_protocol_enabled()
    if not production and not reserved:
        return  # Ordinary local development and unit tests do not need a live DB at startup.

    url = get_database_url()
    expected_name = os.getenv("DB_EXPECTED_NAME", "").strip()
    if production and (not expected_name or expected_name in ("yabs_salon_dev", "yabs_salon_test")):
        raise RuntimeError("Production DB_EXPECTED_NAME must identify a non-development database")
    if production and url.database != expected_name:
        raise RuntimeError("Configured database does not match DB_EXPECTED_NAME")

    # No secrets, connection URLs, or driver exception details enter startup errors.
    try:
        with get_engine().connect() as connection:
            actual_name = connection.scalar(text("SELECT current_database()"))
            schema = connection.scalar(text("SELECT current_schema()"))
            revision_count = connection.scalar(text("SELECT count(*) FROM public.alembic_version"))
            revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            attempts_table = connection.scalar(text("SELECT to_regclass('public.sale_attempts')"))
    except Exception:
        raise RuntimeError("Database startup verification failed") from None
    if actual_name != url.database or (production and actual_name != expected_name):
        raise RuntimeError("Connected database identity does not match configuration")
    if schema != "public" or revision_count != 1 or revision != EXPECTED_REVISION or attempts_table is None:
        raise RuntimeError("Database migration is incompatible with this application")
