"""Serialize sale writers per user/key; allow nonblocking status checks.

The lock is transaction-scoped. Callers own the transaction and must keep it
open through the idempotency claim and sale write. PostgreSQL uniqueness remains
the final safeguard; hash collisions only cause unnecessary serialization.
"""

import hashlib
from uuid import UUID

from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.orm import Session


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
