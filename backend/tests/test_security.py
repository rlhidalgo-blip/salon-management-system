import hashlib
from datetime import timedelta

import pytest

from app.core import config, security


def test_argon2id_password_hash_and_verification() -> None:
    password = "synthetic-test-password"
    stored_hash = security.hash_password(password)

    assert stored_hash.startswith("$argon2id$")
    assert password not in stored_hash
    assert security.verify_password(password, stored_hash)
    assert not security.verify_password("wrong-password", stored_hash)
    assert not security.verify_password(password, "not-an-argon2-hash")


def test_session_tokens_are_distinct_and_sha256_hashed() -> None:
    tokens = {security.generate_session_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 random bytes, URL-safe encoded
    token = next(iter(tokens))
    digest = security.hash_session_token(token)
    assert len(digest) == 64
    assert digest == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert digest == security.hash_session_token(token)
    assert digest != token
    assert security.verify_session_token(token, digest)
    assert not security.verify_session_token("different-token", digest)


def test_production_cookie_config_is_secure_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("AUTH_COOKIE_MODE", raising=False)

    settings = config.get_auth_config()
    assert settings.cookie_name == "__Host-salon_session"
    assert settings.cookie_secure is True
    assert settings.cookie_httponly is True
    assert settings.cookie_samesite == "lax"
    assert settings.cookie_path == "/"
    assert settings.cookie_domain is None
    assert settings.inactivity_timeout == timedelta(hours=8)


def test_localhost_cookie_mode_is_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "localhost")

    settings = config.get_auth_config()
    assert settings.cookie_name == "salon_session_dev"
    assert settings.cookie_secure is False
    assert settings.cookie_httponly is True
    assert settings.cookie_samesite == "lax"
    assert settings.inactivity_timeout == timedelta(hours=8)


def test_invalid_cookie_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("AUTH_COOKIE_MODE", "unsafe")

    with pytest.raises(ValueError, match="AUTH_COOKIE_MODE"):
        config.get_auth_config()
