"""
categorizer/ai_categorizer.py

AI-powered categorizer using Ollama (local LLM, default llama3).
- Checks SQLite cache first — never sends the same description twice.
- Falls back gracefully to rule-based categorizer if Ollama is unavailable.
- Also produces a clean_description (friendly label) alongside category/subcategory.
- All data stays on the local machine. No external API calls.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import requests

from categorizer.rule_categorizer import categorize
from categorizer.description_cleaner import clean_description as rule_clean

logger = logging.getLogger(__name__)

# Fallback valid categories — used when the DB is not available.
_FALLBACK_VALID_CATEGORIES = {
    "income", "housing", "subscriptions", "groceries", "restaurants",
    "transport", "health", "shopping", "entertainment", "transfers",
    "cash", "admin", "uncategorized",
}

_FALLBACK_SYSTEM_PROMPT = """You are a financial transaction labeler for a Spanish bank account.
Given a raw bank transaction description, output ONLY a JSON object with three fields:
  "category": one of [income, housing, subscriptions, groceries, restaurants, transport, health, shopping, entertainment, transfers, cash, admin, uncategorized]
  "subcategory": a short English snake_case label (e.g. "rent", "supermarket", "fast_food", "fuel")
  "clean_description": a very short human-friendly label in Spanish (2-4 words max, e.g. "Mercadona", "Amazon", "Gasolina", "Parking", "Netflix", "Cajero", "Peajes", "Nómina")

Do not output anything other than the JSON object. No explanation, no markdown fences."""


def _build_system_prompt(valid_categories: set[str]) -> str:
    cat_list = ", ".join(sorted(valid_categories))
    return f"""You are a financial transaction labeler for a Spanish bank account.
Given a raw bank transaction description, output ONLY a JSON object with three fields:
  "category": one of [{cat_list}]
  "subcategory": a short English snake_case label (e.g. "rent", "supermarket", "fast_food", "fuel")
  "clean_description": a very short human-friendly label in Spanish (2-4 words max, e.g. "Mercadona", "Amazon", "Gasolina", "Parking", "Netflix", "Cajero", "Peajes", "Nómina")

Do not output anything other than the JSON object. No explanation, no markdown fences."""


def _load_valid_categories_from_store(store) -> set[str]:
    """Load top-level category ids from the SqliteStore."""
    try:
        cats = store.get_categories()
        top_level = {c["id"] for c in cats if c["parent_id"] is None}
        if top_level:
            return top_level
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load categories from store: %s", exc)
    return set()


class AiCategorizer:
    """
    Thin wrapper around Ollama's local REST API.
    Uses SQLite as a persistent cache to avoid repeat LLM calls.
    Handles both category/subcategory and clean_description in a single LLM call.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3",
        cache_path: str | Path = "data/category_cache.db",
        store=None,  # optional SqliteStore for dynamic category list
    ):
        self._url = ollama_url.rstrip("/")
        self._model = model
        self._cache_path = Path(cache_path)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_cache()
        self._ollama_available: bool | None = None  # lazy check

        # Build valid categories and system prompt from DB if available
        if store is not None:
            db_cats = _load_valid_categories_from_store(store)
        else:
            db_cats = set()

        self._valid_categories = db_cats if db_cats else _FALLBACK_VALID_CATEGORIES
        self._system_prompt = _build_system_prompt(self._valid_categories)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def categorize_transaction(self, tx: dict) -> dict:
        description = tx["description"]

        # 1. Rules first — fast, deterministic, no IO
        rule_cat, rule_sub = categorize(description)
        rule_label = rule_clean(description)
        rules_matched = rule_cat != "uncategorized" or rule_label is not None

        if rules_matched:
            return {
                **tx,
                "category": rule_cat,
                "subcategory": rule_sub,
                "category_source": "rule",
                "clean_description": rule_label,
                "clean_description_source": "rule" if rule_label else None,
            }

        # 2. Cache — result from a previous AI session
        cached = self._cache_get(description)
        if cached:
            return {
                **tx,
                "category": cached["category"],
                "subcategory": cached["subcategory"],
                "category_source": "cache",
                "clean_description": cached["clean_description"],
                "clean_description_source": "cache",
            }

        # 3. Ollama — only for descriptions unknown to rules and not yet cached
        if self._is_ollama_available():
            result = self._call_ollama(description)
            if result:
                self._cache_set(
                    description,
                    result["category"],
                    result["subcategory"],
                    result.get("clean_description"),
                )
                return {
                    **tx,
                    "category": result["category"],
                    "subcategory": result["subcategory"],
                    "category_source": "ai",
                    "clean_description": result.get("clean_description"),
                    "clean_description_source": "ai",
                }

        # 4. Pure rule fallback (Ollama unavailable, nothing cached)
        return {
            **tx,
            "category": rule_cat,
            "subcategory": rule_sub,
            "category_source": "rule",
            "clean_description": rule_label,
            "clean_description_source": "rule" if rule_label else None,
        }

    # ------------------------------------------------------------------
    # Ollama interaction
    # ------------------------------------------------------------------

    def _is_ollama_available(self) -> bool:
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            resp = requests.get(f"{self._url}/api/tags", timeout=2)
            self._ollama_available = resp.status_code == 200
        except Exception:  # noqa: BLE001
            self._ollama_available = False
        if not self._ollama_available:
            logger.warning("Ollama not available at %s — using rule-based categorizer only.", self._url)
        return self._ollama_available

    def _call_ollama(self, description: str) -> dict | None:
        payload = {
            "model": self._model,
            "prompt": f'Transaction: "{description}"\n\nClassify it.',
            "system": self._system_prompt,
            "stream": False,
        }
        try:
            resp = requests.post(f"{self._url}/api/generate", json=payload, timeout=30)
            resp.raise_for_status()
            raw_response = resp.json().get("response", "")
            return self._parse_llm_response(raw_response, self._valid_categories)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama call failed: %s", exc)
            return None

    @staticmethod
    def _parse_llm_response(raw: str, valid_categories: set[str]) -> dict | None:
        """Extract JSON from LLM response, tolerating minor formatting quirks."""
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()
        try:
            data = json.loads(raw)
            category = data.get("category", "uncategorized")
            subcategory = data.get("subcategory", "other")
            clean = data.get("clean_description") or None
            if category not in valid_categories:
                category = "uncategorized"
            return {
                "category": category,
                "subcategory": str(subcategory),
                "clean_description": str(clean).strip() if clean else None,
            }
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Could not parse LLM response: %r", raw[:200])
            return None

    # ------------------------------------------------------------------
    # SQLite cache
    # ------------------------------------------------------------------

    def _init_cache(self) -> None:
        with sqlite3.connect(self._cache_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS category_cache (
                    description_hash      TEXT PRIMARY KEY,
                    description           TEXT NOT NULL,
                    category              TEXT NOT NULL,
                    subcategory           TEXT NOT NULL,
                    clean_description     TEXT,
                    source                TEXT NOT NULL DEFAULT 'ai',
                    created_at            TEXT DEFAULT (datetime('now'))
                )
            """)
            # Migrate existing cache tables that predate clean_description column
            try:
                conn.execute("ALTER TABLE category_cache ADD COLUMN clean_description TEXT")
            except Exception:  # noqa: BLE001
                pass  # column already exists
            conn.commit()

    def _cache_get(self, description: str) -> dict | None:
        key = self._hash(description)
        with sqlite3.connect(self._cache_path) as conn:
            row = conn.execute(
                "SELECT category, subcategory, clean_description FROM category_cache WHERE description_hash = ?",
                (key,),
            ).fetchone()
        if row:
            return {"category": row[0], "subcategory": row[1], "clean_description": row[2]}
        return None

    def _cache_set(
        self,
        description: str,
        category: str,
        subcategory: str,
        clean_description: str | None,
    ) -> None:
        key = self._hash(description)
        with sqlite3.connect(self._cache_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO category_cache
                   (description_hash, description, category, subcategory, clean_description, source)
                   VALUES (?, ?, ?, ?, ?, 'ai')""",
                (key, description[:500], category, subcategory, clean_description),
            )
            conn.commit()

    @staticmethod
    def _hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()
