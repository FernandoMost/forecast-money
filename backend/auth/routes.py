"""
auth/routes.py — Authentication endpoints.

  POST  /auth/register   — Create a new account
  POST  /auth/login      — Exchange credentials for a JWT in an httpOnly cookie
  POST  /auth/logout     — Clear the auth cookie
  GET   /auth/me         — Return the current authenticated user

Token storage strategy: httpOnly cookie named 'access_token'.
This prevents XSS-based token theft since JavaScript cannot read httpOnly cookies.
SameSite=Lax prevents CSRF for same-origin navigation; credentials=True is set
in the CORS config so cross-origin requests (frontend → backend) include cookies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError

from api.deps import get_settings, get_user_store
from auth.models import LoginRequest, RegisterRequest, TokenResponse, UserOut
from auth.security import create_access_token, hash_password, verify_password
from db.user_store import UserStore

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days in seconds


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,   # set to True in production (HTTPS only) — controlled by COOKIE_SECURE env
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    response: Response,
    settings=Depends(get_settings),
    user_store: UserStore = Depends(get_user_store),
):
    """
    Register a new user account and set the auth cookie.
    Returns the new user profile (no password).
    """
    hashed = hash_password(body.password)
    try:
        user = user_store.create_user(
            email=body.email,
            hashed_pw=hashed,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    token = create_access_token(
        data={"sub": user["id"]},
        secret_key=settings.secret_key,
        algorithm=settings.algorithm,
        expires_minutes=settings.access_token_expire_minutes,
    )
    # Apply COOKIE_SECURE from settings (True in prod, False in dev)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )
    return TokenResponse(
        message="Registration successful",
        user=UserOut(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            is_active=bool(user["is_active"]),
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    settings=Depends(get_settings),
    user_store: UserStore = Depends(get_user_store),
):
    """
    Authenticate with email + password.
    Sets an httpOnly cookie with the JWT. Returns the user profile.
    """
    user = user_store.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["hashed_pw"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    token = create_access_token(
        data={"sub": user["id"]},
        secret_key=settings.secret_key,
        algorithm=settings.algorithm,
        expires_minutes=settings.access_token_expire_minutes,
    )
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )
    return TokenResponse(
        message="Login successful",
        user=UserOut(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            is_active=bool(user["is_active"]),
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout")
def logout(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"message": "Logged out"}


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
def me(
    request: Request,
    settings=Depends(get_settings),
    user_store: UserStore = Depends(get_user_store),
):
    """Return the currently authenticated user, or 401 if not logged in."""
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    try:
        from auth.security import decode_token
        payload = decode_token(token, settings.secret_key, settings.algorithm)
        user_id: str = payload.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = user_store.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    return UserOut(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        is_active=bool(user["is_active"]),
    )
