"""
api/deps.py — FastAPI dependency injection.
Settings and shared singletons (store) are created once and reused.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    db_path: Path = Path("data/finance.db")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_store():
    """Returns the SQLite store."""
    from db.sqlite_store import SqliteStore
    return SqliteStore(get_settings().db_path)
