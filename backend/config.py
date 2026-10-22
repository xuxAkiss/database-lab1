"""Project-local .env configuration; process environment takes precedence."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = field(repr=False)
    mongodb_db: str
    db_check_timeout_ms: int


def read_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    uri = os.environ.get("MONGODB_URI", "").strip()
    database = os.environ.get("MONGODB_DB", "").strip()
    try:
        timeout = int(os.environ.get("DB_CHECK_TIMEOUT_MS", "5000"))
    except ValueError:
        raise ValueError("DB_CHECK_TIMEOUT_MS must be an integer.") from None
    if not uri or not database:
        raise ValueError("MONGODB_URI and MONGODB_DB must be configured.")
    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise ValueError("MONGODB_URI has an unsupported scheme.")
    if not 500 <= timeout <= 10000:
        raise ValueError("DB_CHECK_TIMEOUT_MS must be between 500 and 10000.")
    return Settings(uri, database, timeout)
