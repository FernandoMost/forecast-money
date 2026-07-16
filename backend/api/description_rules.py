"""
api/description_rules.py — CRUD for description_rules (shared.db) + suggestion engine.

Rules are stored in data/shared.db (description_rules table) and shared across
all users. The legacy clean_description_rules.yaml is no longer the source of
truth — it was migrated into the DB on first startup.

Endpoints:
  GET    /description-rules                — list all rules (with per-user match counts)
  POST   /description-rules                — add a new rule
  PUT    /description-rules/{label}        — update label/patterns for an existing rule
  DELETE /description-rules/{label}        — remove a rule
  GET    /description-suggestions          — groups of uncleaned descriptions for review
  POST   /description-rules/apply          — save rule(s) + trigger recategorize
"""

from __future__ import annotations

import re
import logging
import unicodedata
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_store, get_shared_store, get_current_user
from categorizer.description_cleaner import reload_rules as reload_clean_rules
from categorizer.rule_categorizer import reload_rules as reload_category_rules
from categorizer.rule_categorizer import categorize_transaction
from db.sqlite_store import SqliteStore
from db.shared_store import SharedStore

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DescriptionRule(BaseModel):
    label: str
    patterns: list[str]
    match_count: int = 0


class RuleListResponse(BaseModel):
    rules: list[DescriptionRule]
    total: int


class RuleCreateRequest(BaseModel):
    label: str
    patterns: list[str]
    position: int | None = None


class RuleUpdateRequest(BaseModel):
    new_label: str | None = None
    patterns: list[str] | None = None


class RuleDeleteResponse(BaseModel):
    deleted: bool
    label: str


class SuggestionMember(BaseModel):
    raw: str
    count: int


class SuggestionGroup(BaseModel):
    canonical: str
    suggested_label: str
    suggested_patterns: list[str]
    members: list[dict]
    total_count: int


class SuggestionsResponse(BaseModel):
    groups: list[SuggestionGroup]
    uncovered_total: int


class ApplyRulesRequest(BaseModel):
    rules: list[RuleCreateRequest]


class ApplyRulesResponse(BaseModel):
    saved: int
    updated: int


# ---------------------------------------------------------------------------
# Helper — match counts from the user's own DB
# ---------------------------------------------------------------------------

def _count_matches(store: SqliteStore) -> dict[str, int]:
    """Return {label: count} for all transactions with a clean_description."""
    with store._connect() as conn:
        rows = conn.execute(
            """SELECT clean_description, COUNT(*) as c
               FROM transactions
               WHERE clean_description IS NOT NULL
               GROUP BY clean_description"""
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def _reload_all() -> None:
    reload_clean_rules()
    reload_category_rules()


# ---------------------------------------------------------------------------
# GET /description-rules
# ---------------------------------------------------------------------------

@router.get("/description-rules", response_model=RuleListResponse)
def list_rules(
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    raw = shared.get_all_rules()
    counts = _count_matches(store)
    rules = [
        DescriptionRule(
            label=entry["label"],
            patterns=entry["patterns"],
            match_count=counts.get(entry["label"], 0),
        )
        for entry in raw
    ]
    return RuleListResponse(rules=rules, total=len(rules))


# ---------------------------------------------------------------------------
# POST /description-rules
# ---------------------------------------------------------------------------

@router.post("/description-rules", response_model=DescriptionRule, status_code=201)
def create_rule(
    body: RuleCreateRequest,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    if not body.patterns:
        raise HTTPException(status_code=422, detail="At least one pattern is required.")
    try:
        rule = shared.create_rule(body.label, body.patterns, body.position)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _reload_all()
    return DescriptionRule(label=rule["label"], patterns=rule["patterns"], match_count=0)


# ---------------------------------------------------------------------------
# PUT /description-rules/{label}
# ---------------------------------------------------------------------------

@router.put("/description-rules/{label}", response_model=DescriptionRule)
def update_rule(
    label: str,
    body: RuleUpdateRequest,
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    if body.patterns is not None and not body.patterns:
        raise HTTPException(status_code=422, detail="At least one pattern is required.")
    try:
        updated = shared.update_rule(label, body.new_label, body.patterns)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Rule '{label}' not found.")
    _reload_all()
    counts = _count_matches(store)
    return DescriptionRule(
        label=updated["label"],
        patterns=updated["patterns"],
        match_count=counts.get(updated["label"], 0),
    )


# ---------------------------------------------------------------------------
# DELETE /description-rules/{label}
# ---------------------------------------------------------------------------

@router.delete("/description-rules/{label}", response_model=RuleDeleteResponse)
def delete_rule(
    label: str,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    deleted = shared.delete_rule(label)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule '{label}' not found.")
    _reload_all()
    return RuleDeleteResponse(deleted=True, label=label)


# ---------------------------------------------------------------------------
# Suggestion engine
# ---------------------------------------------------------------------------

_NOISE_TOKENS = {
    "COMPRA", "PAGO", "CARGO", "ABONO", "INGRESO", "TRANSFERENCIA",
    "INMEDIATA", "RECIBO", "LIQUIDACION", "COMISION", "CUOTA",
    "TPV", "POS", "OPE", "BIZUM", "SEPA", "DE", "A", "EN", "EL",
    "LA", "LOS", "LAS", "DEL", "AL", "Y", "S.L", "SL", "SA", "S.A",
    "ES", "COM", "NET", "WWW", "HTTP", "HTTPS",
}

_NOISE_PATTERNS = [
    re.compile(r"^\d+$"),
    re.compile(r"^[A-Z0-9]{6,}$"),
    re.compile(r"^\d{1,2}[/\-]\d{1,2}([/\-]\d{2,4})?$"),
    re.compile(r"^\*+$"),
]


def _normalize(description: str) -> str:
    upper = description.upper()
    nfkd = unicodedata.normalize("NFKD", upper)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    tokens = re.split(r"[\s\-\*\.,/\\|]+", cleaned)
    significant = [
        tok for tok in tokens
        if tok and tok not in _NOISE_TOKENS and not any(p.match(tok) for p in _NOISE_PATTERNS)
    ]
    return " ".join(significant)


def _title_case(canonical: str) -> str:
    return " ".join(w.capitalize() for w in canonical.split())


def _common_tokens(descriptions: list[str]) -> list[str]:
    if not descriptions:
        return []
    token_sets = [set(_normalize(d).split()) for d in descriptions]
    common = token_sets[0]
    for s in token_sets[1:]:
        common &= s
    return sorted(t for t in common if len(t) >= 3)


def _prefix_key(canonical: str, min_len: int = 4) -> str:
    parts = canonical.split()
    if parts and len(parts[0]) >= min_len:
        return parts[0]
    return canonical


@router.get("/description-suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    with store._connect() as conn:
        rows = conn.execute(
            """SELECT description, COUNT(*) as c
               FROM transactions
               WHERE clean_description IS NULL
               GROUP BY description
               ORDER BY c DESC"""
        ).fetchall()

    if not rows:
        return SuggestionsResponse(groups=[], uncovered_total=0)

    uncovered_total = len(rows)
    raw_to_canonical: dict[str, str] = {}
    raw_freq: dict[str, int] = {}
    for raw, count in rows:
        canonical = _normalize(raw)
        raw_to_canonical[raw] = canonical if canonical else raw.upper()
        raw_freq[raw] = count

    canonical_groups: dict[str, list[str]] = defaultdict(list)
    for raw, canonical in raw_to_canonical.items():
        canonical_groups[canonical].append(raw)

    prefix_map: dict[str, str] = {}
    merged: dict[str, list[str]] = defaultdict(list)
    for canonical, members in canonical_groups.items():
        prefix = _prefix_key(canonical)
        if prefix in prefix_map:
            merged[prefix_map[prefix]].extend(members)
        else:
            prefix_map[prefix] = canonical
            merged[canonical].extend(members)

    groups: list[SuggestionGroup] = []
    for canonical, members in merged.items():
        total_count = sum(raw_freq[m] for m in members)
        common = _common_tokens(members)
        if not common:
            norm = _normalize(members[0]).split()
            common = [norm[0]] if norm else [members[0][:8]]
        groups.append(SuggestionGroup(
            canonical=canonical,
            suggested_label=_title_case(canonical),
            suggested_patterns=common,
            members=[{"raw": m, "count": raw_freq[m]} for m in sorted(members, key=lambda m: -raw_freq[m])],
            total_count=total_count,
        ))

    groups.sort(key=lambda g: -g.total_count)
    return SuggestionsResponse(groups=groups[:limit], uncovered_total=uncovered_total)


# ---------------------------------------------------------------------------
# POST /description-rules/apply  — save rules + recategorize in one call
# ---------------------------------------------------------------------------

@router.post("/description-rules/apply", response_model=ApplyRulesResponse)
def apply_rules(
    body: ApplyRulesRequest,
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    saved = 0
    for rule in body.rules:
        if not rule.patterns:
            continue
        if shared.rule_exists(rule.label):
            shared.update_rule(rule.label, patterns=rule.patterns)
        else:
            shared.create_rule(rule.label, rule.patterns, rule.position)
        saved += 1

    _reload_all()

    all_txs = store.get_all_descriptions()
    categorized = [categorize_transaction(tx) for tx in all_txs]
    updated = store.bulk_update_categories(categorized)

    return ApplyRulesResponse(saved=saved, updated=updated)
