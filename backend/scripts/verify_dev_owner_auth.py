r"""Interactive, in-process check of the existing development Owner auth flow.

Run from backend/: .\.venv\Scripts\python.exe scripts\verify_dev_owner_auth.py
No HTTP server, saved cookie jar, or credentials on the command line are needed.
"""

import getpass
import os
import secrets
import sys
from ipaddress import ip_interface

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_database_url
from app.db.session import get_engine


ORIGIN = "http://127.0.0.1:8000"
COOKIE_NAME = "salon_session_dev"


def verify_target() -> bool:
    url = get_database_url()
    if (url.database, url.host, url.port, url.username) != (
        "yabs_salon_dev", "localhost", 5432, "yabs_app"
    ):
        return False

    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        database, user, address, port = connection.execute(
            text("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port()")
        ).one()
        if (
            database != "yabs_salon_dev"
            or user != "yabs_app"
            or address is None
            or not ip_interface(address).ip.is_loopback
            or port != 5432
        ):
            return False
        revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
        connection.rollback()
        return revision == "20261020_01"


def main() -> int:
    # Process-local settings override .env without changing it. Import the app
    # only after these values are set.
    os.environ["DB_NAME"] = "yabs_salon_dev"
    os.environ["AUTH_COOKIE_MODE"] = "localhost"
    os.environ["AUTH_ALLOWED_ORIGIN"] = ORIGIN
    os.environ["AUTH_RATE_LIMIT_SECRET"] = secrets.token_hex(32)

    try:
        if not verify_target():
            print("Stopped: development database guard failed")
            return 1
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            print("Stopped: hidden interactive input requires a terminal")
            return 1

        password = getpass.getpass("Development Owner password: ")
        if not password:
            print("Stopped: empty password")
            return 1

        from app.main import app

        with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": "dev_owner", "password": password},
                headers={"Origin": ORIGIN},
            )
            del password
            print("POST /login:", login.status_code)
            if login.status_code != 200:
                return 1

            original_cookie = client.cookies.get(COOKIE_NAME)
            csrf = login.json().get("csrf_token")
            if not original_cookie or not csrf:
                print("Stopped: expected cookie or CSRF value missing")
                return 1

            me = client.get("/api/v1/auth/me", headers={"Origin": ORIGIN})
            role_ok = (
                me.status_code == 200
                and me.json().get("user", {}).get("username") == "dev_owner"
                and me.json().get("user", {}).get("role") == "Owner"
            )
            print("GET /me:", me.status_code)
            print("Owner role verified:", role_ok)

            logout = client.post(
                "/api/v1/auth/logout",
                headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            )
            print("POST /logout:", logout.status_code)
            if logout.status_code != 204:
                return 1

        # New client has no cookie jar; replay the original cookie in memory to
        # test PostgreSQL revocation, not merely browser-side cookie clearing.
        with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as replay_client:
            replay = replay_client.get(
                "/api/v1/auth/me",
                headers={"Origin": ORIGIN, "Cookie": f"{COOKIE_NAME}={original_cookie}"},
            )
            print("GET /me with revoked cookie:", replay.status_code)
            return 0 if role_ok and replay.status_code == 401 else 1
    except (KeyboardInterrupt, EOFError):
        print("Stopped: interactive input cancelled")
        return 1
    except Exception:
        # Do not print driver errors, request objects, response bodies, or traces:
        # they may contain credentials or session material.
        print("Stopped: verification error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
