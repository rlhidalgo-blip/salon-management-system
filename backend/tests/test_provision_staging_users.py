"""Staging bootstrap safety checks; these tests never connect to PostgreSQL."""

from pathlib import Path

import pytest

from scripts import provision_staging_users as staging


def test_wrong_target_refused_before_environment_is_loaded(tmp_path, monkeypatch):
    environment = tmp_path / ".env.staging"
    environment.write_text(
        "DB_HOST=localhost\nDB_PORT=5432\nDB_NAME=yabs_salon_dev\n"
        "DB_USER=yabs_app\nDB_PASSWORD=synthetic\nDB_SSLMODE=verify-full\n"
        f"PGSSLROOTCERT={tmp_path.as_posix()}\n", encoding="utf-8",
    )
    monkeypatch.setattr(staging, "STAGING_ENV", environment)
    with pytest.raises(staging.Refused, match="target"):
        staging.load_target()


def test_existing_credential_file_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / ".env.staging-accounts"
    path.write_text("existing-credential-marker", encoding="utf-8")
    monkeypatch.setattr(staging, "CREDENTIALS", path)
    with pytest.raises(staging.Refused, match="already exists"):
        staging.save_credentials({"staging_owner": "synthetic-a", "staging_cashier": "synthetic-b"})
    assert path.read_text(encoding="utf-8") == "existing-credential-marker"


def test_credentials_are_restricted_before_passwords_are_written(tmp_path, monkeypatch):
    path = tmp_path / ".env.staging-accounts"
    monkeypatch.setattr(staging, "CREDENTIALS", path)
    observed = []

    def restrict(empty_file: Path):
        observed.append(empty_file.read_bytes())

    monkeypatch.setattr(staging, "restrict_credentials_file", restrict)
    staging.save_credentials({"staging_owner": "synthetic-a", "staging_cashier": "synthetic-b"})
    assert observed == [b""]
    assert "synthetic-a" in path.read_text(encoding="utf-8")
