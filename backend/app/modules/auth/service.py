"""PostgreSQL-backed opaque sessions; the caller owns commit and rollback.

Future API handlers must commit session creation before issuing an auth cookie,
and commit revocation before returning a successful logout response. A real
two-connection revocation/refresh race test remains required before production.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_auth_config
from app.core.security import generate_session_token, hash_session_token
from app.modules.auth.models import AuthSession
from app.modules.users.models import User


@dataclass(frozen=True)
class CreatedSession:
    id: UUID
    token: str  # Return to the cookie-setting caller only; never persist or log.
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    id: UUID
    user_id: int
    role: str  # Read from the current User row, never cached in AuthSession.


def _lock_user(session: Session, user_id: int) -> User | None:
    return session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _lock_session(session: Session, token_hash: str, user_id: int) -> AuthSession | None:
    return session.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash, AuthSession.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _database_now(session: Session) -> datetime:
    # PostgreSQL clock_timestamp() is sampled after lock waits, unlike now().
    return session.execute(select(func.clock_timestamp())).scalar_one()


def create_session(session: Session, user_id: int) -> CreatedSession | None:
    """Create one independent session for a currently active account."""
    user = _lock_user(session, user_id)
    if user is None or not user.active:
        return None

    now = _database_now(session)
    token = generate_session_token()
    record = AuthSession(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_session_token(token),
        created_at=now,
        last_activity_at=now,
        expires_at=now + get_auth_config().inactivity_timeout,
    )
    session.add(record)
    session.flush()  # Persist inside the caller's transaction, not a commit.
    return CreatedSession(id=record.id, token=token, expires_at=record.expires_at)


def validate_session(session: Session, token: str) -> AuthenticatedSession | None:
    """Refresh a valid session; reject expired, revoked, or disabled accounts."""
    token_hash = hash_session_token(token)
    user_id = session.scalar(select(AuthSession.user_id).where(AuthSession.token_hash == token_hash))
    if user_id is None:
        return None

    # Lock order is always User first, then AuthSession. Re-check state after
    # both locks; a concurrent logout/deactivation may have won the race.
    user = _lock_user(session, user_id)
    if user is None:
        return None
    record = _lock_session(session, token_hash, user_id)
    if record is None:
        return None
    now = _database_now(session)
    if not user.active or record.revoked_at is not None or record.expires_at <= now:
        return None

    record.last_activity_at = now
    record.expires_at = now + get_auth_config().inactivity_timeout
    return AuthenticatedSession(id=record.id, user_id=user.id, role=user.role)


def revoke_session(session: Session, token: str) -> bool:
    """Revoke only the supplied session, including one already expired."""
    token_hash = hash_session_token(token)
    user_id = session.scalar(select(AuthSession.user_id).where(AuthSession.token_hash == token_hash))
    if user_id is None or _lock_user(session, user_id) is None:
        return False
    record = _lock_session(session, token_hash, user_id)
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = _database_now(session)
    return True


def revoke_all_sessions(session: Session, user_id: int) -> int:
    """Revoke every currently unrevoked session belonging to one account."""
    if _lock_user(session, user_id) is None:
        return 0
    now = _database_now(session)
    result = session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount
