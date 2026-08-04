"""
api/category_rules.py — CRUD for category_rules (shared.db) + category suggestion engine.

Category rules are stored in data/shared.db and shared across all users.
They replace config/category_rules.yaml as the source of truth (migrated on startup).

Each description_rule can also have an associated category_id (takes priority over
these rules when categorizing — see rule_categorizer.py).

Endpoints:
  GET    /category-rules                   — list all rules (with per-user match counts)
  POST   /category-rules                   — create a new rule
  PUT    /category-rules/{id}              — update category/subcategory/patterns/position
  DELETE /category-rules/{id}              — remove a rule
  POST   /category-rules/apply             — save rule(s) + trigger recategorize for current user
  GET    /category-suggestions             — groups of categorized-description but uncategorized txs
  POST   /category-suggestions/dismiss     — permanently hide a suggestion
  POST   /category-suggestions/apply       — assign category to a group + optionally create rule
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_store, get_shared_store, get_current_user
from api.models import (
    CategoryRuleItem,
    CategoryRuleListResponse,
    CategoryRuleCreateRequest,
    CategoryRuleUpdateRequest,
    CategoryRuleDeleteResponse,
    CategorySuggestionGroup,
    CategorySuggestionsResponse,
    CategorySuggestionApplyRequest,
    CategorySuggestionDismissRequest,
    ApplyCategoryRulesResponse,
)
from categorizer.rule_categorizer import reload_rules as reload_category_rules, categorize_transaction
from categorizer.description_cleaner import reload_rules as reload_clean_rules
from db.sqlite_store import SqliteStore
from db.shared_store import SharedStore

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_category_matches(store: SqliteStore) -> dict[str, int]:
    """Return {category: count} for all transactions."""
    with store._connect() as conn:
        rows = conn.execute(
            """SELECT category, COUNT(*) as c
               FROM transactions
               WHERE category IS NOT NULL AND category != 'uncategorized'
               GROUP BY category"""
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def _reload_all() -> None:
    reload_clean_rules()
    reload_category_rules()


def _recategorize_all(store: SqliteStore) -> int:
    """Re-apply all rules to all non-manual transactions. Returns count updated."""
    strip_config = store.get_strip_config()
    rows = store.get_all_descriptions()
    if not rows:
        return 0
    categorized = [categorize_transaction(row, strip_config=strip_config) for row in rows]
    return store.bulk_update_categories(categorized)


# ---------------------------------------------------------------------------
# GET /category-rules
# ---------------------------------------------------------------------------

@router.get("/category-rules", response_model=CategoryRuleListResponse)
def list_category_rules(
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    raw = shared.get_all_category_rules()
    counts = _count_category_matches(store)
    rules = [
        CategoryRuleItem(
            id=entry["id"],
            category=entry["category"],
            subcategory=entry["subcategory"],
            patterns=entry["patterns"],
            position=entry["position"],
            match_count=counts.get(entry["category"], 0),
            created_at=entry.get("created_at"),
        )
        for entry in raw
    ]
    return CategoryRuleListResponse(rules=rules, total=len(rules))


# ---------------------------------------------------------------------------
# POST /category-rules
# ---------------------------------------------------------------------------

@router.post("/category-rules", response_model=CategoryRuleItem, status_code=201)
def create_category_rule(
    body: CategoryRuleCreateRequest,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    if not body.patterns:
        raise HTTPException(status_code=422, detail="At least one pattern is required.")
    rule = shared.create_category_rule(
        category=body.category,
        patterns=body.patterns,
        subcategory=body.subcategory,
        position=body.position,
    )
    _reload_all()
    return CategoryRuleItem(
        id=rule["id"],
        category=rule["category"],
        subcategory=rule["subcategory"],
        patterns=rule["patterns"],
        position=rule["position"],
        match_count=0,
        created_at=rule.get("created_at"),
    )


# ---------------------------------------------------------------------------
# PUT /category-rules/{id}
# ---------------------------------------------------------------------------

@router.put("/category-rules/{rule_id}", response_model=CategoryRuleItem)
def update_category_rule(
    rule_id: int,
    body: CategoryRuleUpdateRequest,
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    if body.patterns is not None and not body.patterns:
        raise HTTPException(status_code=422, detail="At least one pattern is required.")

    from db.shared_store import _UNSET
    sub = body.subcategory if body.subcategory is not None else _UNSET

    updated = shared.update_category_rule(
        rule_id,
        category=body.category,
        subcategory=sub,
        patterns=body.patterns,
        position=body.position,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Category rule {rule_id} not found.")
    _reload_all()
    counts = _count_category_matches(store)
    return CategoryRuleItem(
        id=updated["id"],
        category=updated["category"],
        subcategory=updated["subcategory"],
        patterns=updated["patterns"],
        position=updated["position"],
        match_count=counts.get(updated["category"], 0),
        created_at=updated.get("created_at"),
    )


# ---------------------------------------------------------------------------
# DELETE /category-rules/{id}
# ---------------------------------------------------------------------------

@router.delete("/category-rules/{rule_id}", response_model=CategoryRuleDeleteResponse)
def delete_category_rule(
    rule_id: int,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    deleted = shared.delete_category_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Category rule {rule_id} not found.")
    _reload_all()
    return CategoryRuleDeleteResponse(deleted=True, id=rule_id)


# ---------------------------------------------------------------------------
# POST /category-rules/apply  — reload + recategorize all transactions
# ---------------------------------------------------------------------------

@router.post("/category-rules/apply", response_model=ApplyCategoryRulesResponse)
def apply_category_rules(
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """Reload category rules from DB and re-apply to all non-manual transactions."""
    _reload_all()
    updated = _recategorize_all(store)
    return ApplyCategoryRulesResponse(updated=updated)


# ---------------------------------------------------------------------------
# GET /category-suggestions
# ---------------------------------------------------------------------------

@router.get("/category-suggestions", response_model=CategorySuggestionsResponse)
def get_category_suggestions(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    """
    Returns groups of transactions that have a clean_description but are uncategorized
    (category IS NULL or 'uncategorized'), excluding dismissed ones.
    """
    dismissed = shared.get_dismissed_category_suggestions()
    groups_raw = store.get_uncategorized_by_clean_description()

    uncovered_total = sum(1 for g in groups_raw if g["clean_description"] not in dismissed)
    filtered = [g for g in groups_raw if g["clean_description"] not in dismissed]

    groups = [
        CategorySuggestionGroup(
            clean_description=g["clean_description"],
            count=g["count"],
            latest_date=g["latest_date"],
        )
        for g in filtered[:limit]
    ]
    return CategorySuggestionsResponse(groups=groups, uncovered_total=uncovered_total)


# ---------------------------------------------------------------------------
# POST /category-suggestions/dismiss
# ---------------------------------------------------------------------------

@router.post("/category-suggestions/dismiss", status_code=204)
def dismiss_category_suggestion(
    body: CategorySuggestionDismissRequest,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    """Permanently dismiss a clean_description from category suggestions."""
    shared.add_dismissed_category_suggestion(body.clean_description)


# ---------------------------------------------------------------------------
# POST /category-suggestions/apply
# ---------------------------------------------------------------------------

@router.post("/category-suggestions/apply")
def apply_category_suggestion(
    body: CategorySuggestionApplyRequest,
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    """
    Assign a category to all transactions matching clean_description.
    Optionally create a category_rule that maps the clean_description pattern to the category.
    Transactions already manually categorized are NOT overwritten.
    """
    updated = store.bulk_set_category_for_clean_description(
        body.clean_description, body.category, body.subcategory
    )

    rule_id: int | None = None
    if body.create_rule:
        # Create or find a category_rule whose pattern matches this clean_description
        import re as _re
        pattern = _re.escape(body.clean_description)
        rule = shared.create_category_rule(
            category=body.category,
            patterns=[pattern],
            subcategory=body.subcategory,
        )
        rule_id = rule["id"]
        _reload_all()

    return {
        "updated": updated,
        "rule_id": rule_id,
        "clean_description": body.clean_description,
        "category": body.category,
        "subcategory": body.subcategory,
    }
