"""
main.py — FastAPI application entry point.

Run with:
    uvicorn main:app --reload --port 8000

For production (VPS), run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the backend directory is on the Python path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.description_rules import router as description_rules_router
from auth.routes import router as auth_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Forecast Money API",
    description="Privacy-first personal finance analyzer. All data stays local.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(description_rules_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Startup — migrate YAML rules into shared.db (one-shot, non-destructive)
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_migrate_rules() -> None:
    """
    On first startup, import rules from the legacy clean_description_rules.yaml
    into data/shared.db if the description_rules table is empty.

    This is a one-shot migration: subsequent restarts are no-ops because
    the table will already have rows.
    """
    try:
        from api.deps import get_settings
        from db.shared_store import SharedStore

        settings = get_settings()
        shared = SharedStore(settings.shared_db_path)

        yaml_candidates = [
            Path(__file__).parent.parent / "config" / "clean_description_rules.yaml",
            Path(__file__).parent / "config" / "clean_description_rules.yaml",
        ]
        yaml_path = next((p for p in yaml_candidates if p.exists()), yaml_candidates[0])

        imported = shared.migrate_from_yaml(yaml_path)
        if imported:
            logger.info("Startup: migrated %d rules from YAML → shared.db", imported)

        # Reload the in-memory rules so description_cleaner uses the DB immediately
        from categorizer.description_cleaner import reload_rules
        count = reload_rules()
        logger.info("Startup: %d description rules loaded into memory.", count)

    except Exception as exc:
        logger.error("Startup rule migration failed: %s", exc)


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Finance Analyzer API — visit /docs for the interactive API explorer."}
