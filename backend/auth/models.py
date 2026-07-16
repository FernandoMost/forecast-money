"""
auth/models.py — Pydantic models for auth endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    is_active: bool


class TokenResponse(BaseModel):
    message: str
    user: UserOut
