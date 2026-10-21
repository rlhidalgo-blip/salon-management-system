"""Explicit, development-only first Owner provisioning; never runs at startup."""

import argparse
import getpass
import hmac
from ipaddress import ip_interface

from sqlalchemy import Engine, insert, select, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_database_url
from app.core.security import hash_password
from app.db.model_registry import get_model_metadata
from app.db.session import get_engine
from app.modules.users.models import User


DEV_DATABASE = "yabs_salon_dev"
EXPECTED_REVISION = "20261020_01"


class ProvisioningRefused(Exception):
    """A safety check failed; no account should be created."""


def verify_configured_target(url: URL) -> None:
    if (url.database, url.host, url.port, url.username) != (DEV_DATABASE, "localhost", 5432, "yabs_app"):
        raise ProvisioningRefused("Configured database is not the approved local development target")


def verify_dev_database(connection: Connection) -> None:
    database, user, address, port = connection.execute(
        text("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port()")
    ).one()
    if (
        database != DEV_DATABASE
        or user != "yabs_app"
        or address is None
        or not ip_interface(address).ip.is_loopback
        or port != 5432
    ):
        raise ProvisioningRefused("Connected database is not the approved local development target")

    expected_tables = set(get_model_metadata().tables)
    actual_tables = set(
        connection.execute(
            text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
        ).scalars()
    )
    if actual_tables != expected_tables | {"alembic_version"}:
        raise ProvisioningRefused("Development schema does not contain exactly the approved tables")
    revisions = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
    if revisions != [EXPECTED_REVISION]:
        raise ProvisioningRefused("Initial Alembic revision is not applied")


def provision_owner(engine: Engine, url: URL, username: str, password: str) -> None:
    """Create one Owner atomically; database unique constraint resolves races."""
    verify_configured_target(url)
    if not username or username != username.strip() or not password:
        raise ProvisioningRefused("Supply a nonblank username without surrounding spaces and a password")

    try:
        with engine.begin() as connection:
            verify_dev_database(connection)  # Recheck on the writing connection.
            connection.execute(text("SELECT pg_advisory_xact_lock(870631301)"))
            if connection.scalar(select(User.id).where(User.username == username)) is not None:
                raise ProvisioningRefused("Account already exists; nothing was changed")
            if connection.scalar(select(User.id).where(User.role == "Owner").limit(1)) is not None:
                raise ProvisioningRefused("An Owner already exists; nothing was changed")
            connection.execute(
                insert(User).values(username=username, password_hash=hash_password(password), role="Owner", active=True)
            )
    except IntegrityError:
        # Never print the exception: driver diagnostics can contain bound values.
        raise ProvisioningRefused("Account conflict; nothing was changed") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first Owner in the local development database only")
    parser.add_argument("--username", required=True, help="Explicit development Owner username")
    args = parser.parse_args()
    try:
        url = get_database_url()
        verify_configured_target(url)
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            verify_dev_database(connection)
            connection.rollback()
        password = getpass.getpass("New development Owner password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if not hmac.compare_digest(password, confirmation):
            raise ProvisioningRefused("Passwords did not match; nothing was changed")
        provision_owner(engine, url, args.username, password)
    except (ProvisioningRefused, SQLAlchemyError, ValueError, EOFError, KeyboardInterrupt) as exc:
        message = str(exc) if isinstance(exc, ProvisioningRefused) else "Provisioning failed; no account created"
        print(message)
        return 1
    print("Development Owner created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
