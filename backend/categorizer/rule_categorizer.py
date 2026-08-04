"""
categorizer/rule_categorizer.py

Regex-based categorizer. Rules are loaded from data/shared.db (category_rules table).
Falls back to config/category_rules.yaml (legacy) only if the DB has no rules.

Categorization priority per transaction:
  1. description_rule.category_id — if the matched description rule has a linked
     category, that category takes absolute precedence.
  2. category_rules table — first regex match wins (ordered by position ASC).
  3. Fallback: ('uncategorized', 'other')

To apply changes: edit via POST /api/v1/category-rules or UI, then
POST /api/v1/recategorize to re-apply to all stored transactions.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CategoryRule:
    category: str
    subcategory: str
    patterns: list[re.Pattern]


# ---------------------------------------------------------------------------
# Module-level rule cache — loaded once at import time, reloaded on demand
# ---------------------------------------------------------------------------

_RULES: list[CategoryRule] = []
_DESC_RULE_CATEGORIES: dict[str, tuple[str, str]] = {}
# Maps description_rule label → (category, subcategory) for rules with a linked category


def _get_shared_store():
    """Lazy import to avoid circular dependencies at module level."""
    try:
        from api.deps import get_settings
        from db.shared_store import SharedStore
        settings = get_settings()
        return SharedStore(settings.shared_db_path)
    except Exception:
        return None


def _load_rules_from_db() -> tuple[list[CategoryRule], dict[str, tuple[str, str]]]:
    """
    Load category_rules from shared.db.
    Also load description_rule → category associations.
    Returns (category_rules, desc_rule_categories).
    """
    shared = _get_shared_store()
    if shared is None:
        logger.warning("SharedStore unavailable — falling back to YAML rules.")
        return _load_rules_from_yaml(), {}

    try:
        raw_cat_rules = shared.get_all_category_rules()
        category_rules = []
        for entry in raw_cat_rules:
            try:
                compiled = [re.compile(p, re.IGNORECASE) for p in entry["patterns"]]
                category_rules.append(CategoryRule(
                    category=entry["category"],
                    subcategory=entry["subcategory"] or "other",
                    patterns=compiled,
                ))
            except re.error as exc:
                logger.error("Invalid pattern in category rule id=%s: %s", entry["id"], exc)

        # Load description_rule → category associations
        desc_rule_categories: dict[str, tuple[str, str]] = {}
        for rule in shared.get_all_rules():
            if rule.get("category_id"):
                desc_rule_categories[rule["label"]] = (
                    rule["category_id"],
                    rule.get("subcategory_id") or "other",
                )

        logger.debug(
            "Loaded %d category rules and %d description-rule→category associations from shared.db",
            len(category_rules), len(desc_rule_categories),
        )
        return category_rules, desc_rule_categories

    except Exception as exc:
        logger.error("Failed to load category rules from DB (%s) — falling back to YAML.", exc)
        return _load_rules_from_yaml(), {}


def _load_rules_from_yaml() -> list[CategoryRule]:
    """Legacy fallback: load from config/category_rules.yaml."""
    import yaml
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "category_rules.yaml",
        Path(__file__).parent.parent / "config" / "category_rules.yaml",
    ]
    config_path = next((p for p in candidates if p.exists()), None)
    if config_path is None:
        logger.warning("category_rules.yaml not found — no category rules loaded.")
        return []
    try:
        with config_path.open(encoding="utf-8") as f:
            import yaml as _yaml
            raw = _yaml.safe_load(f) or []
        rules = []
        for entry in raw:
            if not entry.get("category") or not entry.get("subcategory"):
                continue
            try:
                compiled = [re.compile(p, re.IGNORECASE) for p in entry.get("patterns", [])]
                rules.append(CategoryRule(
                    category=entry["category"],
                    subcategory=entry["subcategory"],
                    patterns=compiled,
                ))
            except re.error as exc:
                logger.error("Invalid YAML pattern: %s", exc)
        logger.debug("Loaded %d category rules from %s (legacy YAML)", len(rules), config_path)
        return rules
    except Exception as exc:
        logger.error("Failed to load category_rules.yaml: %s", exc)
        return []


def reload_rules() -> int:
    """Reload category rules from shared.db. Returns the number of rules loaded."""
    global _RULES, _DESC_RULE_CATEGORIES
    _RULES, _DESC_RULE_CATEGORIES = _load_rules_from_db()
    return len(_RULES)


# Trigger initial load
reload_rules()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(description: str) -> tuple[str, str]:
    """
    Returns (category, subcategory) for a description string.
    Falls back to ('uncategorized', 'other') if no rule matches.
    This does NOT consider description_rule associations — use categorize_transaction
    for the full priority chain.
    """
    for rule in _RULES:
        for pattern in rule.patterns:
            if pattern.search(description):
                return rule.category, rule.subcategory
    return "uncategorized", "other"


def categorize_transaction(tx: dict, strip_config: list[dict] | None = None) -> dict:
    """
    Returns the transaction dict with category, stripped_description and
    clean_description filled in.

    Priority:
      1. If the matched description_rule has category_id set → use that category.
      2. Evaluate category_rules (regex) in position order → first match wins.
      3. Fallback: ('uncategorized', 'other')
    """
    from categorizer.description_cleaner import clean_transaction as _clean_tx
    cleaned = _clean_tx(tx, strip_config=strip_config)

    # Priority 1: description_rule has an explicit category association
    clean_desc = cleaned.get("clean_description")
    if clean_desc and clean_desc in _DESC_RULE_CATEGORIES:
        cat, sub = _DESC_RULE_CATEGORIES[clean_desc]
        return {
            **cleaned,
            "category": cat,
            "subcategory": sub,
            "category_source": "desc_rule",
        }

    # Priority 2: category_rules regex matching
    desc_for_cat = cleaned.get("stripped_description") or tx["description"]
    cat, sub = categorize(desc_for_cat)

    return {
        **cleaned,
        "category": cat,
        "subcategory": sub,
        "category_source": "rule",
    }
