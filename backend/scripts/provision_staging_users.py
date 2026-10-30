"""Explicit two-account bootstrap for the approved empty Neon staging database.

Never runs at application startup. Credentials are generated locally and kept
only in a Git-ignored file with a restricted Windows ACL.
"""

import argparse
import csv
import io
import os
import secrets
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import Connection, URL
from sqlalchemy.pool import NullPool

from app.core.config import get_database_url
from app.core.security import hash_password
from app.db.model_registry import get_model_metadata
from app.modules.users.models import User


ROOT = Path(__file__).resolve().parents[2]
STAGING_ENV = ROOT / "backend" / "env" / ".env.staging"
CREDENTIALS = ROOT / "backend" / "env" / ".env.staging-accounts"
HOST = "ep-green-bird-b3zrmv3d.c-4.ap-southeast-1.aws.neon.tech"
DATABASE = "neondb"
ROLE = "neondb_owner"
REVISION = "20261027_01"
ACCOUNTS = (("staging_owner", "Owner"), ("staging_cashier", "Cashier"))


class Refused(Exception):
    """A safe reason to stop before or during staging provisioning."""


def load_target() -> URL:
    values = dotenv_values(STAGING_ENV)
    required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
                "DB_SSLMODE", "PGSSLROOTCERT")
    if any(not values.get(key) for key in required):
        raise Refused("Staging configuration is incomplete")
    if (values["DB_HOST"].strip() != HOST or values["DB_PORT"] != "5432"
            or values["DB_NAME"] != DATABASE or values["DB_USER"] != ROLE
            or values["DB_SSLMODE"] != "verify-full"
            or not Path(values["PGSSLROOTCERT"]).is_file()):
        raise Refused("Staging target or TLS configuration differs from approval")
    if os.getenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0") != "0":
        raise Refused("Sale-attempt protocol must remain disabled")
    for key in required:
        os.environ[key] = values[key]
    url = get_database_url()
    if (url.host, url.port, url.database, url.username, url.query.get("sslmode")) != (
            HOST, 5432, DATABASE, ROLE, "verify-full"):
        raise Refused("Application database target differs from approval")
    return url


def verify_connection(connection: Connection, *, require_empty_users: bool) -> None:
    driver = connection.connection.driver_connection
    if not driver.pgconn.ssl_in_use or driver.info.host != HOST:
        raise Refused("Connected TLS or host check failed")
    identity = connection.execute(text(
        "SELECT current_database(), current_user, current_schema(), inet_server_port()"
    )).one()
    if tuple(identity) != (DATABASE, ROLE, "public", 5432):
        raise Refused("Connected database identity differs from approval")
    schemas = connection.execute(text(
        "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
        "AND nspname <> 'information_schema' ORDER BY 1"
    )).scalars().all()
    if schemas != ["public"]:
        raise Refused("Unexpected database schema")
    tables = set(connection.execute(text(
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'"
    )).scalars())
    if tables != set(get_model_metadata().tables) | {"alembic_version"}:
        raise Refused("Staging schema differs from approved models")
    revisions = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
    if revisions != [REVISION]:
        raise Refused("Staging Alembic revision differs from approval")
    # Existing failed-login audits are expected. Everything else must be empty.
    for table in sorted(tables - {"alembic_version", "audit_events", "users"}):
        if connection.scalar(text(f"SELECT count(*) FROM public.{table}")) != 0:
            raise Refused("Staging contains unexpected application records")
    unexpected_audits = connection.scalar(text(
        "SELECT count(*) FROM public.audit_events "
        "WHERE event_type <> 'LoginFailure' OR actor_user_id IS NOT NULL"
    ))
    if unexpected_audits != 0:
        raise Refused("Staging contains unexpected audit events")
    if require_empty_users and connection.scalar(text("SELECT count(*) FROM public.users")) != 0:
        raise Refused("Staging users already exist; nothing was changed")


def restrict_credentials_file(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
    )
    rows = list(csv.reader(io.StringIO(identity.stdout)))
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].startswith("S-1-"):
        raise Refused("Could not identify the local user for credential protection")
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{rows[0][1]}:(F)"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise Refused("Could not restrict staging credential file access")


def save_credentials(passwords: dict[str, str]) -> None:
    if CREDENTIALS.exists():
        raise Refused("Staging credential file already exists; inspect account state")
    content = (
        f"STAGING_OWNER_USERNAME={ACCOUNTS[0][0]}\n"
        f"STAGING_OWNER_PASSWORD={passwords[ACCOUNTS[0][0]]}\n"
        f"STAGING_CASHIER_USERNAME={ACCOUNTS[1][0]}\n"
        f"STAGING_CASHIER_PASSWORD={passwords[ACCOUNTS[1][0]]}\n"
    )
    descriptor = os.open(CREDENTIALS, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    # Restrict the empty file before any password is written to disk.
    restrict_credentials_file(CREDENTIALS)
    CREDENTIALS.write_text(content, encoding="utf-8")


def provision(url: URL) -> None:
    passwords = {name: secrets.token_urlsafe(32) for name, _ in ACCOUNTS}
    hashes = {name: hash_password(passwords[name]) for name, _ in ACCOUNTS}
    save_credentials(passwords)  # Keep the only recoverable copies before DB commit.
    engine = create_engine(
        url, poolclass=NullPool,
        connect_args={"connect_timeout": 8, "options": "-c statement_timeout=15000 -c lock_timeout=3000"},
    )
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(870631302)"))
            verify_connection(connection, require_empty_users=True)
            connection.execute(insert(User), [
                {"username": name, "password_hash": hashes[name], "role": role, "active": True}
                for name, role in ACCOUNTS
            ])
    finally:
        engine.dispose()
    # A separate connection verifies the committed state without reading hashes.
    verify_engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 8})
    try:
        with verify_engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            verify_connection(connection, require_empty_users=False)
            users = connection.execute(text("SELECT username, role, active FROM public.users ORDER BY username")).all()
            connection.rollback()
    finally:
        verify_engine.dispose()
    if sorted(tuple(row) for row in users) != sorted((name, role, True) for name, role in ACCOUNTS):
        raise Refused("Committed account verification failed; inspect staging manually")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded synthetic Neon staging account bootstrap")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only preflight")
    mode.add_argument("--create", action="store_true", help="Create both accounts atomically")
    args = parser.parse_args()
    try:
        url = load_target()
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 8})
        try:
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                verify_connection(connection, require_empty_users=True)
                connection.rollback()
        finally:
            engine.dispose()
        print("Staging target, TLS, schema and empty users verified")
        if args.create:
            provision(url)
            print("Staging accounts verified: staging_owner=Owner active; staging_cashier=Cashier active")
            print("Passwords saved only in backend/env/.env.staging-accounts")
    except Refused as exc:
        print(f"Provisioning refused: {exc}")
        return 1
    except Exception:
        # Driver errors may contain bound values; never echo raw diagnostics.
        print("Provisioning stopped; inspect staging account state before any retry")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
