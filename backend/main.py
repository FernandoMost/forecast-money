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
from api.category_rules import router as category_rules_router
from api.backup import router as backup_router
from api.prorations import router as prorations_router
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
app.include_router(category_rules_router, prefix="/api/v1")
app.include_router(backup_router, prefix="/api/v1")
app.include_router(prorations_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Startup — migrate legacy data into shared.db (one-shot, non-destructive)
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_migrate_rules() -> None:
    """
    On first startup:
    1. Migrate legacy clean_description_rules.yaml → description_rules table (if empty)
    2. Seed categories from _DEFAULT_CATEGORIES into shared.db (if empty)
    3. Migrate legacy category_rules.yaml → category_rules table (if empty)
    4. Reload in-memory rule caches.

    All migrations are one-shot: subsequent restarts are no-ops because the tables
    will already have rows.
    """
    try:
        from api.deps import get_settings
        from db.shared_store import SharedStore

        settings = get_settings()
        shared = SharedStore(settings.shared_db_path)

        # 1. Description rules: legacy YAML → DB
        yaml_candidates = [
            Path(__file__).parent.parent / "config" / "clean_description_rules.yaml",
            Path(__file__).parent / "config" / "clean_description_rules.yaml",
        ]
        yaml_path = next((p for p in yaml_candidates if p.exists()), yaml_candidates[0])
        imported = shared.migrate_from_yaml(yaml_path)
        if imported:
            logger.info("Startup: migrated %d description rules from YAML → shared.db", imported)

        # 2. Categories: seed from default taxonomy
        _DEFAULT_CATEGORIES = [
            {"id": "income",        "name": "Income",        "parent_id": None, "color": "#84cc16", "role": "income",        "position": 0},
            {"id": "housing",       "name": "Housing",       "parent_id": None, "color": "#6366f1", "role": "fixed",         "position": 1},
            {"id": "subscriptions", "name": "Subscriptions", "parent_id": None, "color": "#a855f7", "role": "subscriptions", "position": 2},
            {"id": "groceries",     "name": "Groceries",     "parent_id": None, "color": "#22c55e", "role": "needs",         "position": 3},
            {"id": "restaurants",   "name": "Restaurants",   "parent_id": None, "color": "#f97316", "role": "leisure",       "position": 4},
            {"id": "transport",     "name": "Transport",     "parent_id": None, "color": "#0ea5e9", "role": "needs",         "position": 5},
            {"id": "health",        "name": "Health",        "parent_id": None, "color": "#14b8a6", "role": "needs",         "position": 6},
            {"id": "shopping",      "name": "Shopping",      "parent_id": None, "color": "#ec4899", "role": "wants",         "position": 7},
            {"id": "entertainment", "name": "Entertainment", "parent_id": None, "color": "#eab308", "role": "leisure",       "position": 8},
            {"id": "transfers",     "name": "Transfers",     "parent_id": None, "color": "#94a3b8", "role": "other",         "position": 9},
            {"id": "cash",          "name": "Cash",          "parent_id": None, "color": "#78716c", "role": "other",         "position": 10},
            {"id": "admin",         "name": "Admin",         "parent_id": None, "color": "#64748b", "role": "needs",         "position": 11},
            {"id": "uncategorized", "name": "Uncategorized", "parent_id": None, "color": "#d1d5db", "role": "other",         "position": 12},
            {"id": "payroll",               "name": "Payroll",          "parent_id": "income",        "color": None, "role": None, "position": 0},
            {"id": "transfer_in",           "name": "Transfer in",      "parent_id": "income",        "color": None, "role": None, "position": 1},
            {"id": "bizum_in",              "name": "Bizum in",         "parent_id": "income",        "color": None, "role": None, "position": 2},
            {"id": "refund",                "name": "Refund",           "parent_id": "income",        "color": None, "role": None, "position": 3},
            {"id": "paypal_in",             "name": "PayPal in",        "parent_id": "income",        "color": None, "role": None, "position": 4},
            {"id": "rent",                  "name": "Rent",             "parent_id": "housing",       "color": None, "role": None, "position": 0},
            {"id": "utilities_electricity", "name": "Electricity",      "parent_id": "housing",       "color": None, "role": None, "position": 1},
            {"id": "utilities_water",       "name": "Water",            "parent_id": "housing",       "color": None, "role": None, "position": 2},
            {"id": "utilities_heating",     "name": "Heating",          "parent_id": "housing",       "color": None, "role": None, "position": 3},
            {"id": "internet_phone",        "name": "Internet / Phone", "parent_id": "housing",       "color": None, "role": None, "position": 4},
            {"id": "streaming",             "name": "Streaming",        "parent_id": "subscriptions", "color": None, "role": None, "position": 0},
            {"id": "gym",                   "name": "Gym",              "parent_id": "subscriptions", "color": None, "role": None, "position": 1},
            {"id": "sports_club",           "name": "Sports club",      "parent_id": "subscriptions", "color": None, "role": None, "position": 2},
            {"id": "paypal_sub",            "name": "PayPal sub",       "parent_id": "subscriptions", "color": None, "role": None, "position": 3},
            {"id": "pagatelia",             "name": "Pagatelia",        "parent_id": "subscriptions", "color": None, "role": None, "position": 4},
            {"id": "other_sub",             "name": "Other sub",        "parent_id": "subscriptions", "color": None, "role": None, "position": 5},
            {"id": "supermarket",           "name": "Supermarket",      "parent_id": "groceries",     "color": None, "role": None, "position": 0},
            {"id": "other_food_shop",       "name": "Other food shop",  "parent_id": "groceries",     "color": None, "role": None, "position": 1},
            {"id": "fast_food",             "name": "Fast food",        "parent_id": "restaurants",   "color": None, "role": None, "position": 0},
            {"id": "restaurant",            "name": "Restaurant",       "parent_id": "restaurants",   "color": None, "role": None, "position": 1},
            {"id": "cafe_bakery",           "name": "Café / Bakery",    "parent_id": "restaurants",   "color": None, "role": None, "position": 2},
            {"id": "bar_pub",               "name": "Bar / Pub",        "parent_id": "restaurants",   "color": None, "role": None, "position": 3},
            {"id": "parking",               "name": "Parking",          "parent_id": "transport",     "color": None, "role": None, "position": 0},
            {"id": "fuel",                  "name": "Fuel",             "parent_id": "transport",     "color": None, "role": None, "position": 1},
            {"id": "rideshare",             "name": "Rideshare",        "parent_id": "transport",     "color": None, "role": None, "position": 2},
            {"id": "public_transit",        "name": "Public transit",   "parent_id": "transport",     "color": None, "role": None, "position": 3},
            {"id": "train_station",         "name": "Train",            "parent_id": "transport",     "color": None, "role": None, "position": 4},
            {"id": "tyre_service",          "name": "Tyres",            "parent_id": "transport",     "color": None, "role": None, "position": 5},
            {"id": "pharmacy",              "name": "Pharmacy",         "parent_id": "health",        "color": None, "role": None, "position": 0},
            {"id": "medical",               "name": "Medical",          "parent_id": "health",        "color": None, "role": None, "position": 1},
            {"id": "online",                "name": "Online",           "parent_id": "shopping",      "color": None, "role": None, "position": 0},
            {"id": "clothing",              "name": "Clothing",         "parent_id": "shopping",      "color": None, "role": None, "position": 1},
            {"id": "electronics",           "name": "Electronics",      "parent_id": "shopping",      "color": None, "role": None, "position": 2},
            {"id": "general",               "name": "General",          "parent_id": "shopping",      "color": None, "role": None, "position": 3},
            {"id": "cinema",                "name": "Cinema",           "parent_id": "entertainment", "color": None, "role": None, "position": 0},
            {"id": "events",                "name": "Events",           "parent_id": "entertainment", "color": None, "role": None, "position": 1},
            {"id": "gaming",                "name": "Gaming",           "parent_id": "entertainment", "color": None, "role": None, "position": 2},
            {"id": "rent_contribution",     "name": "Rent contribution","parent_id": "transfers",     "color": None, "role": None, "position": 0},
            {"id": "bizum_out",             "name": "Bizum out",        "parent_id": "transfers",     "color": None, "role": None, "position": 1},
            {"id": "transfer_out",          "name": "Transfer out",     "parent_id": "transfers",     "color": None, "role": None, "position": 2},
            {"id": "atm_withdrawal",        "name": "ATM withdrawal",   "parent_id": "cash",          "color": None, "role": None, "position": 0},
            {"id": "city_tax",              "name": "City tax",         "parent_id": "admin",         "color": None, "role": None, "position": 0},
            {"id": "travel_tickets",        "name": "Travel tickets",   "parent_id": "admin",         "color": None, "role": None, "position": 1},
            {"id": "other",                 "name": "Other",            "parent_id": "uncategorized", "color": None, "role": None, "position": 0},
        ]
        seeded = shared.migrate_categories_from_seed(_DEFAULT_CATEGORIES)
        if seeded:
            logger.info("Startup: seeded %d categories into shared.db", seeded)

        # 3. Category rules: legacy YAML → DB
        cat_yaml_candidates = [
            Path(__file__).parent.parent / "config" / "category_rules.yaml",
            Path(__file__).parent / "config" / "category_rules.yaml",
        ]
        cat_yaml_path = next((p for p in cat_yaml_candidates if p.exists()), cat_yaml_candidates[0])
        imported_cat = shared.migrate_category_rules_from_yaml(cat_yaml_path)
        if imported_cat:
            logger.info("Startup: migrated %d category rules from YAML → shared.db", imported_cat)

        # 4. Reload in-memory caches
        from categorizer.description_cleaner import reload_rules as reload_clean
        from categorizer.rule_categorizer import reload_rules as reload_cat
        desc_count = reload_clean()
        cat_count = reload_cat()
        logger.info(
            "Startup: %d description rules, %d category rules loaded into memory.",
            desc_count, cat_count,
        )

    except Exception as exc:
        logger.error("Startup migration failed: %s", exc)


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Finance Analyzer API — visit /docs for the interactive API explorer."}
