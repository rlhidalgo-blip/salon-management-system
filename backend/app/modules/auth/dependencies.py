"""Browser guards plus request-cached authentication and role dependencies."""

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_auth_api_config, get_auth_config
from app.core.exceptions import ApiError
from app.core.security import csrf_token_for_session, verify_csrf_token
from app.db.session import get_db_session
from app.modules.auth.service import validate_session
from app.modules.users.models import User


def require_allowed_origin(request: Request, *, required: bool) -> None:
    # Browser POSTs without Origin fail closed. GET /me may omit Origin because
    # normal same-origin GET navigation/fetch often does; a supplied one is checked.
    # Fetch Metadata additionally rejects cross-site GETs that lack Origin.
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise ApiError(403, "origin_rejected", "Request origin is not allowed")
    origin = request.headers.get("origin")
    if (required or origin is not None) and origin != get_auth_api_config().allowed_origin:
        raise ApiError(403, "origin_rejected", "Request origin is not allowed")


def require_session_cookie(request: Request) -> str:
    token = request.cookies.get(get_auth_config().cookie_name)
    if not token:
        raise ApiError(401, "unauthenticated", "Authentication required")
    return token


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    role: str
    csrf_token: str


def get_current_principal(request: Request, session: Session = Depends(get_db_session)) -> Principal:
    """Validate once per request, commit refresh, and use the current User row."""
    token = require_session_cookie(request)
    if request.method in ("GET", "HEAD", "OPTIONS"):
        require_allowed_origin(request, required=False)
    else:
        require_state_change_protection(request, token=token)
    with session.begin():
        authenticated = validate_session(session, token)
        if authenticated is None:
            raise ApiError(401, "unauthenticated", "Authentication required")
        # validate_session already locked/reloaded User; Session.get reuses it.
        user = session.get(User, authenticated.user_id)
        if user is None or not user.active:
            raise ApiError(401, "unauthenticated", "Authentication required")
        principal = Principal(
            user_id=user.id,
            username=user.username,
            role=authenticated.role,
            csrf_token=csrf_token_for_session(token),
        )
    return principal


def require_owner(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role != "Owner":
        raise ApiError(403, "forbidden", "Insufficient permissions")
    return principal


def require_owner_or_cashier(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role not in ("Owner", "Cashier"):
        raise ApiError(403, "forbidden", "Insufficient permissions")
    return principal


def require_state_change_protection(request: Request, *, token: str | None = None) -> None:
    """Apply automatically through Principal on protected unsafe requests."""
    token = token if token is not None else require_session_cookie(request)
    require_allowed_origin(request, required=True)
    if not verify_csrf_token(token, request.headers.get("X-CSRF-Token")):
        raise ApiError(403, "csrf_rejected", "CSRF verification failed")
