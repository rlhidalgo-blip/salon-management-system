from collections.abc import Generator
from functools import lru_cache
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the engine on first use; no connection is made at import time."""
    try:
        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    except ValueError as exc:
        raise ValueError("DB pool settings must be integers") from exc
    if not 1 <= pool_size <= 10 or not 0 <= max_overflow <= 10:
        raise ValueError("DB pool settings are outside supported bounds")
    return create_engine(
        get_database_url(), pool_pre_ping=True,
        pool_size=pool_size, max_overflow=max_overflow,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield one session for a request and close it afterward."""
    with get_session_factory()() as session:
        yield session


def check_database_connection() -> bool:
    """Run a read-only query only when this function is explicitly called."""
    try:
        with get_engine().connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1
    except SQLAlchemyError:
        return False
