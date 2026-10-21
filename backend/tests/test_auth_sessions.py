"""Fast session-service checks that do not connect to PostgreSQL."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.security import hash_session_token
from app.modules.auth import service
from app.modules.auth.models import AuthSession
from app.modules.users.models import User


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_create_stores_only_token_hash_and_does_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.scalar.return_value = User(id=7, username="synthetic", password_hash="synthetic", role="Owner", active=True)
    monkeypatch.setattr(service, "_database_now", lambda unused: NOW)
    monkeypatch.setattr(service, "generate_session_token", lambda: "synthetic-raw-token")

    created = service.create_session(session, 7)

    assert created is not None
    record = session.add.call_args.args[0]
    assert isinstance(record, AuthSession)
    assert record.token_hash == hash_session_token(created.token)
    assert record.token_hash != created.token
    assert record.last_activity_at == NOW
    assert record.expires_at == NOW + timedelta(hours=8)
    session.flush.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.parametrize("state", ["valid", "expired", "revoked", "inactive"])
def test_validation_rechecks_locked_state_and_current_role(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    session = MagicMock()
    user = User(id=7, username="synthetic", password_hash="synthetic", role="Cashier", active=state != "inactive")
    record = AuthSession(
        id=uuid4(), user_id=7, token_hash=hash_session_token("raw-token"),
        created_at=NOW - timedelta(hours=2), last_activity_at=NOW - timedelta(hours=2),
        expires_at=NOW if state == "expired" else NOW + timedelta(hours=1),
        revoked_at=NOW - timedelta(minutes=1) if state == "revoked" else None,
    )
    session.scalar.side_effect = [7, user, record]
    monkeypatch.setattr(service, "_database_now", lambda unused: NOW)

    authenticated = service.validate_session(session, "raw-token")

    if state == "valid":
        assert authenticated == service.AuthenticatedSession(record.id, 7, "Cashier")
        assert record.last_activity_at == NOW
        assert record.expires_at == NOW + timedelta(hours=8)
    else:
        assert authenticated is None
        assert record.last_activity_at == NOW - timedelta(hours=2)
    lock_queries = [str(call.args[0].compile(dialect=postgresql.dialect())) for call in session.scalar.call_args_list]
    assert "FROM users" in lock_queries[1] and "FOR UPDATE" in lock_queries[1]
    assert "FROM auth_sessions" in lock_queries[2] and "FOR UPDATE" in lock_queries[2]
    session.commit.assert_not_called()


def test_revoke_all_does_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.scalar.return_value = User(id=7, username="synthetic", password_hash="synthetic", role="Owner")
    session.execute.return_value.rowcount = 2
    monkeypatch.setattr(service, "_database_now", lambda unused: NOW)

    assert service.revoke_all_sessions(session, 7) == 2
    session.commit.assert_not_called()
