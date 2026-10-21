"""Opt-in session tests; all synthetic rows are rolled back from yabs_salon_test."""

import os
from datetime import timedelta
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_auth_config, get_database_url
from app.core.security import hash_session_token
from app.modules.auth.models import AuthSession
from app.modules.auth.service import (
    create_session,
    revoke_all_sessions,
    revoke_session,
    validate_session,
)
from app.modules.users.models import User


class SessionCase:
    def __init__(self, session: Session, marker: str) -> None:
        self.session = session
        self.marker = marker
        self.user_ids: set[int] = set()
        self.session_ids: set[UUID] = set()

    def user(self, role: str = "Owner") -> User:
        user = User(
            username=f"{self.marker}-{role.lower()}",
            password_hash="synthetic-hash-not-a-real-password",
            role=role,
            active=True,
        )
        self.session.add(user)
        self.session.flush()
        self.user_ids.add(user.id)
        return user

    def create(self, user_id: int):
        created = create_session(self.session, user_id)
        assert created is not None
        self.session_ids.add(created.id)
        return created


@pytest.fixture
def db() -> Iterator[SessionCase]:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 for PostgreSQL session tests")

    url = get_database_url()
    if url.database != "yabs_salon_test":
        pytest.fail("Configured database is not yabs_salon_test; no writes attempted")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Connected database is not yabs_salon_test; no writes attempted")
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                pytest.fail("Alembic version table absent; no writes attempted")
            if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != "20261020_01":
                pytest.fail("Expected migration revision absent; no writes attempted")

            connection.rollback()
            outer = connection.begin()
            session = Session(bind=connection, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint")
            case = SessionCase(session, f"integration-session-{uuid4().hex}")
            try:
                yield case
            finally:
                try:
                    session.close()
                finally:
                    if not outer.is_active:
                        pytest.fail("Outer transaction ended unexpectedly; rollback safety lost")
                    outer.rollback()

        with engine.connect() as verifier:
            if verifier.scalar(text("SELECT current_database()")) != "yabs_salon_test":
                pytest.fail("Rollback verification connected to the wrong database")
            if case.user_ids:
                assert verifier.scalar(select(func.count()).select_from(User).where(User.id.in_(case.user_ids))) == 0
            if case.session_ids:
                assert verifier.scalar(
                    select(func.count()).select_from(AuthSession).where(AuthSession.id.in_(case.session_ids))
                ) == 0
    finally:
        engine.dispose()


def test_create_two_independent_sessions_with_only_token_hashes(db: SessionCase) -> None:
    user = db.user()
    first = db.create(user.id)
    second = db.create(user.id)

    assert first.id != second.id
    assert first.token != second.token
    records = db.session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
    assert len(records) == 2
    assert {record.token_hash for record in records} == {
        hash_session_token(first.token), hash_session_token(second.token),
    }
    assert all(record.token_hash not in (first.token, second.token) for record in records)


def test_validation_refreshes_and_rejects_expired_session(db: SessionCase) -> None:
    user = db.user()
    created = db.create(user.id)
    record = db.session.get(AuthSession, created.id)
    database_now = db.session.scalar(select(func.clock_timestamp()))
    record.expires_at = database_now + timedelta(minutes=1)
    db.session.flush()

    authenticated = validate_session(db.session, created.token)
    assert authenticated is not None and authenticated.user_id == user.id and authenticated.role == "Owner"
    assert record.expires_at == record.last_activity_at + get_auth_config().inactivity_timeout

    record.expires_at = database_now - timedelta(seconds=1)
    db.session.flush()
    assert validate_session(db.session, created.token) is None
    assert record.expires_at == database_now - timedelta(seconds=1)


def test_current_role_and_disabled_account_are_checked(db: SessionCase) -> None:
    user = db.user()
    created = db.create(user.id)
    user.role = "Cashier"
    db.session.flush()
    authenticated = validate_session(db.session, created.token)
    assert authenticated is not None and authenticated.role == "Cashier"

    user.active = False
    db.session.flush()
    assert validate_session(db.session, created.token) is None
    assert create_session(db.session, user.id) is None


def test_current_session_revocation_preserves_other_sessions(db: SessionCase) -> None:
    user = db.user()
    first = db.create(user.id)
    second = db.create(user.id)

    assert revoke_session(db.session, first.token)
    db.session.flush()
    assert validate_session(db.session, first.token) is None
    assert validate_session(db.session, second.token) is not None
    assert not revoke_session(db.session, first.token)


def test_account_wide_revocation(db: SessionCase) -> None:
    user = db.user()
    first = db.create(user.id)
    second = db.create(user.id)

    assert revoke_all_sessions(db.session, user.id) == 2
    assert validate_session(db.session, first.token) is None
    assert validate_session(db.session, second.token) is None
    assert revoke_all_sessions(db.session, user.id) == 0
