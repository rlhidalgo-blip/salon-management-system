"""Cross-worker login failure limits backed by scoped, pseudonymous audit events.

Deployment must trust only its configured reverse proxy for client IP handling;
never read arbitrary X-Forwarded-For headers here. Audit JSONB scans and event
retention need performance/operations review before production.
"""

import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy import BigInteger, bindparam, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_auth_api_config
from app.modules.audit.models import AuditEvent


WINDOW = text("INTERVAL '15 minutes'")
ACCOUNT_LIMIT = 5
IP_LIMIT = 20


@dataclass(frozen=True)
class LoginKeys:
    account: str
    ip: str


def login_keys(username: str, client_ip: str) -> LoginKeys:
    secret = get_auth_api_config().rate_limit_secret

    def digest(label: str, value: str) -> str:
        return hmac.new(secret, f"{label}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()

    return LoginKeys(
        account=digest("account", username.strip().casefold()),
        ip=digest("ip", client_ip),
    )


def is_rate_limited(session: Session, keys: LoginKeys) -> bool:
    """Serialize decisions per identifier, then count committed failures."""
    lock_statement = text("SELECT pg_advisory_xact_lock(:key)").bindparams(bindparam("key", type_=BigInteger))
    lock_ids = {
        int.from_bytes(bytes.fromhex(digest[:16]), byteorder="big", signed=True)
        for digest in (keys.account, keys.ip)
    }
    for lock_id in sorted(lock_ids):
        session.execute(lock_statement, {"key": lock_id})

    base = (
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.event_type == "LoginFailure",
            AuditEvent.occurred_at >= func.clock_timestamp() - WINDOW,
        )
    )
    account_count = session.scalar(
        base.where(func.jsonb_extract_path_text(AuditEvent.event_metadata, "account_key") == keys.account)
    )
    ip_count = session.scalar(
        base.where(func.jsonb_extract_path_text(AuditEvent.event_metadata, "ip_key") == keys.ip)
    )
    return account_count >= ACCOUNT_LIMIT or ip_count >= IP_LIMIT


def record_login_failure(session: Session, keys: LoginKeys) -> None:
    """Caller commits this event even though authentication returns 401."""
    session.add(
        AuditEvent(
            actor_user_id=None,
            event_type="LoginFailure",
            resource_type="auth",
            outcome="Failure",
            occurred_at=func.clock_timestamp(),
            event_metadata={"account_key": keys.account, "ip_key": keys.ip},
        )
    )
    session.flush()


def record_login_success(session: Session, user_id: int) -> None:
    session.add(
        AuditEvent(
            actor_user_id=user_id,
            event_type="LoginSuccess",
            resource_type="auth",
            outcome="Success",
            occurred_at=func.clock_timestamp(),
        )
    )
