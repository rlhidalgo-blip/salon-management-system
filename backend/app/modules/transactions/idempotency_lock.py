"""Serialize sale writers per user/key; allow nonblocking status checks.

The lock is transaction-scoped. Callers own the transaction and must keep it
open through the idempotency claim and sale write. PostgreSQL uniqueness remains
the final safeguard; hash collisions only cause unnecessary serialization.
"""

import hashlib
from functools import wraps
from uuid import UUID

from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError


def _lock_id(user_id: int, key: UUID) -> int:
    digest = hashlib.sha256(f"sale:{user_id}:{key}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def lock_sale_key(session: Session, user_id: int, key: UUID) -> None:
    statement = text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
        bindparam("lock_id", type_=BigInteger))
    session.execute(statement, {"lock_id": _lock_id(user_id, key)})


def try_lock_sale_key(session: Session, user_id: int, key: UUID) -> bool:
    statement = text("SELECT pg_try_advisory_xact_lock(:lock_id)").bindparams(
        bindparam("lock_id", type_=BigInteger))
    return session.execute(statement, {"lock_id": _lock_id(user_id, key)}).scalar_one() is True


def bound_sale_waits(session: Session) -> None:
    """Bound this transaction only; never change global PostgreSQL settings."""
    session.execute(text("SET LOCAL lock_timeout = '3s'"))
    session.execute(text("SET LOCAL statement_timeout = '15s'"))


def lock_manual_reference(session: Session, reference: str) -> None:
    """All reservation-aware Manual writes use the same normalized-reference lock."""
    digest = hashlib.sha256(f"paper:{reference}".encode("ascii")).digest()
    lock_id = int.from_bytes(digest[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
        bindparam("lock_id", type_=BigInteger)), {"lock_id": lock_id})


def raise_retryable_sale_wait(exc: DBAPIError) -> None:
    """The caller's transaction must roll back before another same-key attempt."""
    if getattr(exc.orig, "sqlstate", None) in ("55P03", "57014", "40P01"):
        raise ApiError(503, "sale_outcome_uncertain",
                       "Sale outcome is uncertain; check the same key before retrying") from None
    raise exc


def retryable_sale_waits(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DBAPIError as exc:
            raise_retryable_sale_wait(exc)
    return guarded
