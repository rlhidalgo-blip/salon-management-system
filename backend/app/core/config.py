import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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

    return URL.create(
        "postgresql+psycopg",
        username=values["DB_USER"],
        password=values["DB_PASSWORD"],
        host=values["DB_HOST"],
        port=port,
        database=values["DB_NAME"],
    )
