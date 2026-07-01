"""
categorizer/ai_categorizer.py

AI-powered categorizer using Ollama (local LLM, default llama3).
- Checks SQLite cache first — never sends the same description twice.
- Falls back gracefully to rule-based categorizer if Ollama is unavailable.
- All data stays on the local machine. No external API calls.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import requests

from categorizer.rule_categorizer import categorize

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {
    "income", "housing", "subscriptions", "groceries", "restaurants",
    "transport", "health", "shopping", "entertainment", "transfers",
    "cash", "admin", "uncategorized",
}

_SYSTEM_PROMPT = """You are a financial transaction categorizer.
Given a Spanish bank transaction description, output ONLY a JSON object with two fields:
  "category": one of [income, housing, subscriptions, groceries, restaurants, transport, health, shopping, entertainment, transfers, cash, admin, uncategorized]
  "subcategory": a short English snake_case label (e.g. "rent", "supermarket", "fast_food", "fuel")

Do not output anything other than the JSON object. No explanation, no markdown fences."""


class AiCategorizer:
    """
    Thin wrapper around Ollama's local REST API.
    Uses SQLite as a persistent cache to avoid repeat LLM calls.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3",
        cache_path: str | Path = "data/category_cache.db",
    ):
        self._url = ollama_url.rstrip("/")
        self._model = model
        self._cache_path = Path(cache_path)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_cache()
        self._ollama_available: bool | None = None  # lazy check

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def categorize_transaction(self, tx: dict) -> dict:
        description = tx["description"]

        # 1. Try cache
        cached = self._cache_get(description)
        if cached:
            return {**tx, "category": cached["category"], "subcategory": cached["subcategory"], "category_source": "cache"}

        # 2. Try Ollama
        if self._is_ollama_available():
            result = self._call_ollama(description)
            if result:
                self._cache_set(description, result["category"], result["subcategory"])
                return {**tx, **result, "category_source": "ai"}

        # 3. Fallback to rule-based
        category, subcategory = categorize(description)
        return {**tx, "category": category, "subcategory": subcategory, "category_source": "rule"}

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
            "system": _SYSTEM_PROMPT,
            "stream": False,
        }
        try:
            resp = requests.post(f"{self._url}/api/generate", json=payload, timeout=30)
            resp.raise_for_status()
            raw_response = resp.json().get("response", "")
            return self._parse_llm_response(raw_response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama call failed: %s", exc)
            return None

    @staticmethod
    def _parse_llm_response(raw: str) -> dict | None:
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
            if category not in _VALID_CATEGORIES:
                category = "uncategorized"
            return {"category": category, "subcategory": str(subcategory)}
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
                    description_hash TEXT PRIMARY KEY,
                    description      TEXT NOT NULL,
                    category         TEXT NOT NULL,
                    subcategory      TEXT NOT NULL,
                    source           TEXT NOT NULL DEFAULT 'ai',
                    created_at       TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def _cache_get(self, description: str) -> dict | None:
        key = self._hash(description)
        with sqlite3.connect(self._cache_path) as conn:
            row = conn.execute(
                "SELECT category, subcategory FROM category_cache WHERE description_hash = ?",
                (key,),
            ).fetchone()
        if row:
            return {"category": row[0], "subcategory": row[1]}
        return None

    def _cache_set(self, description: str, category: str, subcategory: str) -> None:
        key = self._hash(description)
        with sqlite3.connect(self._cache_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO category_cache
                   (description_hash, description, category, subcategory, source)
                   VALUES (?, ?, ?, ?, 'ai')""",
                (key, description[:500], category, subcategory),
            )
            conn.commit()

    @staticmethod
    def _hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()
