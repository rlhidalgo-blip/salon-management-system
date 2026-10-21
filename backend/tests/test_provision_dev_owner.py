"""Development provisioning safeguards; no live database or account writes."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from app.core.security import verify_password
from app.db.model_registry import get_model_metadata
from scripts.provision_dev_owner import (
    ProvisioningRefused,
    provision_owner,
    verify_configured_target,
    verify_dev_database,
)


def dev_url(**changes: object) -> URL:
    values = dict(
        drivername="postgresql+psycopg",
        username="yabs_app",
        password="synthetic-never-used",
        host="localhost",
        port=5432,
        database="yabs_salon_dev",
    )
    values.update(changes)
    return URL.create(**values)


@pytest.mark.parametrize("change", [
    {"database": "yabs_salon_test"},
    {"database": "yabs_salon_production"},
    {"host": "remote.example"},
    {"username": "postgres"},
    {"port": 5433},
])
def test_configured_target_rejects_other_databases_hosts_and_users(change: dict) -> None:
    with pytest.raises(ProvisioningRefused, match="configured|Configured"):
        verify_configured_target(dev_url(**change))


def fake_connection(*, database="yabs_salon_dev", user="yabs_app", address="::1/128", port=5432,
                    revision="20261020_01", tables=None):
    connection = MagicMock()
    table_names = set(get_model_metadata().tables) | {"alembic_version"} if tables is None else tables
    identity_result = MagicMock()
    identity_result.one.return_value = (database, user, address, port)
    tables_result = MagicMock()
    tables_result.scalars.return_value = list(table_names)
    revision_result = MagicMock()
    revision_result.scalars.return_value.all.return_value = [revision]
    connection.execute.side_effect = [identity_result, tables_result, revision_result]
    return connection


def test_database_guard_accepts_approved_local_schema_and_revision() -> None:
    verify_dev_database(fake_connection())


@pytest.mark.parametrize("change", [
    {"database": "yabs_salon_test"},
    {"user": "postgres"},
    {"address": "192.0.2.10/32"},
    {"port": 5433},
    {"revision": "different"},
    {"tables": {"users", "alembic_version"}},
    {"tables": set(get_model_metadata().tables) | {"alembic_version", "unexpected"}},
])
def test_database_guard_fails_closed(change: dict) -> None:
    with pytest.raises(ProvisioningRefused):
        verify_dev_database(fake_connection(**change))


def test_duplicate_account_refused_without_hash_or_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.return_value = 7
    monkeypatch.setattr("scripts.provision_dev_owner.verify_dev_database", lambda _: None)
    hash_call = MagicMock()
    monkeypatch.setattr("scripts.provision_dev_owner.hash_password", hash_call)

    with pytest.raises(ProvisioningRefused, match="already exists"):
        provision_owner(engine, dev_url(), "existing", "synthetic-password")

    hash_call.assert_not_called()
    assert connection.execute.call_count == 1  # Advisory lock only; no INSERT.


def test_existing_owner_refused_without_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.side_effect = [None, 8]
    monkeypatch.setattr("scripts.provision_dev_owner.verify_dev_database", lambda _: None)
    with pytest.raises(ProvisioningRefused, match="Owner already exists"):
        provision_owner(engine, dev_url(), "another", "synthetic-password")
    assert connection.execute.call_count == 1


def test_insert_uses_argon2id_hash_and_only_approved_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.side_effect = [None, None]
    monkeypatch.setattr("scripts.provision_dev_owner.verify_dev_database", lambda _: None)
    password = "synthetic-password"

    provision_owner(engine, dev_url(), "dev-owner", password)

    statement = connection.execute.call_args.args[0]
    assert statement.table.name == "users"
    values = statement.compile().params
    assert values["username"] == "dev-owner"
    assert values["role"] == "Owner"
    assert values["active"] is True
    assert values["password_hash"].startswith("$argon2id$")
    assert password not in values["password_hash"]
    assert verify_password(password, values["password_hash"])


def test_unique_conflict_is_refused_without_exposing_driver_details(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.side_effect = [None, None]
    connection.execute.side_effect = [MagicMock(), IntegrityError("INSERT", {}, Exception("secret-driver-detail"))]
    monkeypatch.setattr("scripts.provision_dev_owner.verify_dev_database", lambda _: None)
    with pytest.raises(ProvisioningRefused, match="Account conflict") as caught:
        provision_owner(engine, dev_url(), "dev-owner", "synthetic-password")
    assert "secret-driver-detail" not in str(caught.value)


def test_wrong_config_refuses_before_opening_connection() -> None:
    engine = MagicMock()
    with pytest.raises(ProvisioningRefused):
        provision_owner(engine, dev_url(database="other"), "dev-owner", "synthetic-password")
    engine.begin.assert_not_called()
