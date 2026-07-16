"""
api/deps.py — FastAPI dependency injection.

Settings, shared singletons, and the get_current_user dependency that
validates the httpOnly JWT cookie on every protected endpoint.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_COOKIE_NAME = "access_token"


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path("data")
    auth_db_path: Path = Path("data/auth.db")
    users_data_dir: Path = Path("data/users")

    # JWT
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # Cookie — set to True in production (requires HTTPS)
    cookie_secure: bool = False

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# User store (auth.db)
# ---------------------------------------------------------------------------

def get_user_store():
    """Returns the UserStore (auth.db). One instance per request — very cheap."""
    from db.user_store import UserStore
    settings = get_settings()
    return UserStore(settings.auth_db_path)


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------

def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    FastAPI dependency that validates the httpOnly JWT cookie.

    Returns the user dict from auth.db.
    Raises 401 if the cookie is missing, expired, or invalid.
    """
    from auth.security import decode_token
    from db.user_store import UserStore

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please log in.",
        headers={"WWW-Authenticate": "Cookie"},
    )

    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise credentials_exception

    try:
        payload = decode_token(token, settings.secret_key, settings.algorithm)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_store = UserStore(settings.auth_db_path)
    user = user_store.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise credentials_exception

    return user


# ---------------------------------------------------------------------------
# Per-user scoped finance store
# ---------------------------------------------------------------------------

def get_store(current_user: dict = Depends(get_current_user)):
    """
    Returns a SqliteStore scoped to the authenticated user.

    Each user has their own SQLite database at:
        data/users/<user_id>.db

    This is the dependency used by all protected finance endpoints.
    """
    from db.sqlite_store import SqliteStore
    settings = get_settings()
    db_path = settings.users_data_dir / f"{current_user['id']}.db"
    return SqliteStore(db_path)
