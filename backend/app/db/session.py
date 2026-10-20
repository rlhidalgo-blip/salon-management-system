from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the engine on first use; no connection is made at import time."""
    return create_engine(get_database_url(), pool_pre_ping=True)


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
