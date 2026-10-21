"""Initial cookie-session authentication API; no account-management routes."""

from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_auth_config
from app.core.exceptions import ApiError
from app.core.security import csrf_token_for_session, hash_password, verify_password
from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_allowed_origin,
    require_session_cookie,
    require_state_change_protection,
)
from app.modules.auth.rate_limit import is_rate_limited, login_keys, record_login_failure, record_login_success
from app.modules.auth.service import create_session, revoke_session, validate_session
from app.modules.users.models import User


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    # Random, non-account input avoids a hardcoded credential while making
    # unknown and disabled accounts perform an Argon2id verification.
    from secrets import token_urlsafe

    return hash_password(token_urlsafe(32))


# Warm the fake hash once at import, avoiding a first-request timing distinction.
_dummy_password_hash()


@router.post("/login")
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_db_session)) -> JSONResponse:
    require_allowed_origin(request, required=True)
    if request.client is None:
        raise ApiError(500, "client_address_unavailable", "Authentication unavailable")
    keys = login_keys(payload.username, request.client.host)
    created = None
    public_user = None
    failed = False
    with session.begin():
        if is_rate_limited(session, keys):
            raise ApiError(429, "rate_limited", "Too many login attempts", {"Retry-After": "900"})
        user = session.scalar(select(User).where(User.username == payload.username))
        stored_hash = user.password_hash if user is not None and user.active else _dummy_password_hash()
        password_ok = verify_password(payload.password, stored_hash)
        if user is None or not user.active or not password_ok:
            record_login_failure(session, keys)
            failed = True
        else:
            created = create_session(session, user.id)
            if created is None:
                record_login_failure(session, keys)
                failed = True
            else:
                record_login_success(session, user.id)
                public_user = {"id": user.id, "username": user.username, "role": user.role}

    # The transaction has committed before a cookie or success response exists.
    if failed:
        raise ApiError(401, "invalid_credentials", "Invalid username or password")
    assert created is not None and public_user is not None
    cookies = get_auth_config()
    response = JSONResponse({"user": public_user, "csrf_token": csrf_token_for_session(created.token)})
    response.set_cookie(
        key=cookies.cookie_name,
        value=created.token,
        secure=cookies.cookie_secure,
        httponly=cookies.cookie_httponly,
        samesite=cookies.cookie_samesite,
        path=cookies.cookie_path,
        domain=cookies.cookie_domain,
    )
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, session: Session = Depends(get_db_session)) -> Response:
    require_state_change_protection(request)
    token = require_session_cookie(request)
    with session.begin():
        if validate_session(session, token) is None or not revoke_session(session, token):
            raise ApiError(401, "unauthenticated", "Authentication required")

    # Revocation has committed before cookie clearing or successful logout.
    cookies = get_auth_config()
    response = Response(status_code=204)
    response.delete_cookie(
        key=cookies.cookie_name,
        path=cookies.cookie_path,
        domain=cookies.cookie_domain,
        secure=cookies.cookie_secure,
        httponly=cookies.cookie_httponly,
        samesite=cookies.cookie_samesite,
    )
    return response


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict:
    # The shared dependency committed the activity refresh before this runs.
    return {
        "user": {"id": principal.user_id, "username": principal.username, "role": principal.role},
        "csrf_token": principal.csrf_token,
    }
