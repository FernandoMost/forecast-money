"""
auth/security.py — Password hashing and JWT token utilities.

Tokens are designed to be stored as httpOnly cookies, not in localStorage.
The cookie is named 'access_token' and is set by the /auth/login endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of the plain-text password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    data: dict[str, Any],
    secret_key: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    """
    Create a signed JWT access token.

    The 'sub' claim should be the user id (UUID hex).
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload["exp"] = expire
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
    """
    Decode and verify a JWT token.

    Raises jose.JWTError on invalid/expired tokens — callers should catch this.
    """
    return jwt.decode(token, secret_key, algorithms=[algorithm])
