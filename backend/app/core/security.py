"""Password and opaque session-token primitives; no persistence or logging."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_password_hasher = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    """Return an Argon2id hash suitable for the Users.password_hash column."""
    return _password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify without exposing a mismatch or malformed hash to callers."""
    try:
        return _password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_session_token() -> str:
    """Generate an opaque token from 32 cryptographically random bytes."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Return the 64-character SHA-256 digest to persist, never the raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_session_token(token: str, stored_hash: str) -> bool:
    """Use constant-time comparison when checking a token against its digest."""
    return hmac.compare_digest(hash_session_token(token), stored_hash)


def csrf_token_for_session(token: str) -> str:
    """Derive a CSRF value from the HttpOnly-only random session token."""
    return hmac.new(token.encode("utf-8"), b"salon-csrf-v1", hashlib.sha256).hexdigest()


def verify_csrf_token(token: str, submitted: str | None) -> bool:
    return submitted is not None and hmac.compare_digest(csrf_token_for_session(token), submitted)
