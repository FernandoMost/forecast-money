"""
main.py — FastAPI application entry point.

Run with:
    uvicorn main:app --reload --port 8000

For production (VPS), run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the backend directory is on the Python path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from auth.routes import router as auth_router

app = FastAPI(
    title="Forecast Money API",
    description="Privacy-first personal finance analyzer. All data stays local.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
#
# Development: allow the local Next.js dev server.
# Production: ALLOWED_ORIGINS env var controls the list (set to your domain).
#
# credentials=True is required for httpOnly cookies to be sent cross-origin.
# ---------------------------------------------------------------------------

import os

_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,   # required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Finance Analyzer API — visit /docs for the interactive API explorer."}
