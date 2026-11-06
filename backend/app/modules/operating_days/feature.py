"""Default-off calendar write gate, restricted to the local development database."""

import os

from app.core.config import get_auth_config, get_database_url
from app.core.exceptions import ApiError


def require_calendar_writes_ready() -> None:
    # A deployment flag cannot enable writes outside the loopback development
    # database. Keep this check on every write route, even if a UI hides controls.
    if os.getenv("CALENDAR_WRITES_ENABLED", "0") != "1":
        raise ApiError(404, "not_found", "Request failed", headers={"Cache-Control": "no-store"})
    url = get_database_url()
    enabled = (
        os.getenv("APP_ENV", "development") == "development"
        and os.getenv("AUTH_COOKIE_MODE", "production") == "localhost"
        and not get_auth_config().cookie_secure
        and url.host in ("localhost", "127.0.0.1", "::1")
        and url.database == "yabs_salon_dev"
        and not url.query.get("sslmode")
    )
    if not enabled:
        raise ApiError(404, "not_found", "Request failed", headers={"Cache-Control": "no-store"})
