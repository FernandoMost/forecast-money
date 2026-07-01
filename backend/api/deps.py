"""
api/deps.py — FastAPI dependency injection.
Settings and shared singletons (store) are created once and reused.

Store selection:
  - Local mode (default): MONGO_URI is not set → SqliteStore
  - Cloud mode: MONGO_URI is set in environment → MongoStore
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Union

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    db_path: Path = Path("data/finance.db")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    # Set MONGO_URI to enable cloud/MongoDB mode (Phase 5)
    # e.g.  MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/finance
    mongo_uri: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_store():
    """
    Returns the appropriate store based on environment configuration.
    - If MONGO_URI is set: MongoStore (cloud mode)
    - Otherwise: SqliteStore (local mode, default)
    """
    settings = get_settings()

    if settings.mongo_uri:
        try:
            from db.mongo_store import MongoStore
            logger.info("Cloud mode: using MongoDB store.")
            return MongoStore(settings.mongo_uri)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to connect to MongoDB (%s) — falling back to SQLite.", exc)

    from db.sqlite_store import SqliteStore
    return SqliteStore(settings.db_path)
