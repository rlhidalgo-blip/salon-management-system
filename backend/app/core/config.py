import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import URL


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class AuthConfig:
    cookie_name: str
    cookie_secure: bool
    cookie_httponly: bool = True
    cookie_samesite: str = "lax"
    cookie_path: str = "/"
    cookie_domain: None = None
    inactivity_timeout: timedelta = timedelta(hours=8)


def get_auth_config() -> AuthConfig:
    """Use secure production defaults or an explicit localhost-only cookie mode."""
    load_dotenv(ENV_FILE, override=False)
    mode = os.getenv("AUTH_COOKIE_MODE", "production").strip().lower()
    if mode == "production":
        return AuthConfig(cookie_name="__Host-salon_session", cookie_secure=True)
    if mode == "localhost":
        return AuthConfig(cookie_name="salon_session_dev", cookie_secure=False)
    raise ValueError("AUTH_COOKIE_MODE must be production or localhost")


@dataclass(frozen=True)
class AuthApiConfig:
    allowed_origin: str
    rate_limit_secret: bytes


def get_auth_api_config() -> AuthApiConfig:
    """Fail closed when browser origin or pseudonymization key is missing."""
    load_dotenv(ENV_FILE, override=False)
    origin = os.getenv("AUTH_ALLOWED_ORIGIN", "").strip()
    parsed = urlsplit(origin)
    cookie_mode = os.getenv("AUTH_COOKIE_MODE", "production").strip().lower()
    valid_origin = (
        parsed.scheme in ("http", "https")
        and bool(parsed.netloc)
        and parsed.hostname is not None
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and origin == f"{parsed.scheme}://{parsed.netloc}"
    )
    if not valid_origin:
        raise ValueError("AUTH_ALLOWED_ORIGIN must be one exact origin")
    if cookie_mode == "production" and parsed.scheme != "https":
        raise ValueError("Production AUTH_ALLOWED_ORIGIN must use HTTPS")
    if cookie_mode == "localhost" and (
        parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1")
    ):
        raise ValueError("Localhost AUTH_ALLOWED_ORIGIN must use local HTTP")
    if cookie_mode not in ("production", "localhost"):
        raise ValueError("AUTH_COOKIE_MODE must be production or localhost")
    secret = os.getenv("AUTH_RATE_LIMIT_SECRET", "")
    if len(secret.encode("utf-8")) < 32 or secret.startswith("replace_"):
        raise ValueError("AUTH_RATE_LIMIT_SECRET must contain at least 32 bytes")
    return AuthApiConfig(allowed_origin=origin, rate_limit_secret=secret.encode("utf-8"))


def get_database_url() -> URL:
    """Build a PostgreSQL URL from local .env or process environment variables."""
    load_dotenv(ENV_FILE, override=False)

    required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    values = {name: os.getenv(name) for name in required}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"Missing database configuration: {', '.join(missing)}")

    try:
        port = int(values["DB_PORT"])
    except ValueError as exc:
        raise ValueError("DB_PORT must be a valid integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be between 1 and 65535")

    sslmode = os.getenv("DB_SSLMODE", "").strip().lower()
    if sslmode and sslmode not in ("require", "verify-ca", "verify-full"):
        raise ValueError("DB_SSLMODE must be require, verify-ca, or verify-full")
    if values["DB_HOST"].lower().endswith(".neon.tech") and sslmode != "verify-full":
        raise ValueError("Neon connections require DB_SSLMODE=verify-full")

    return URL.create(
        "postgresql+psycopg",
        username=values["DB_USER"],
        password=values["DB_PASSWORD"],
        host=values["DB_HOST"],
        port=port,
        database=values["DB_NAME"],
        query={"sslmode": sslmode} if sslmode else {},
    )
