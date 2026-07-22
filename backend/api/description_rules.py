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
from categorizer.description_cleaner import reload_rules as reload_clean_rules, apply_strip_config
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


class DismissRequest(BaseModel):
    description: str


class MarkCleanRequest(BaseModel):
    description: str   # the raw/stripped description to match against
    label: str         # human-friendly label to store as clean_description


class MarkCleanResponse(BaseModel):
    updated: int
    label: str


class ApplyRulesRequest(BaseModel):
    rules: list[RuleCreateRequest]


class ApplyRulesResponse(BaseModel):
    saved: int
    updated: int


# ---------------------------------------------------------------------------
# Strip config models
# ---------------------------------------------------------------------------

class StripConfigEntry(BaseModel):
    id: int
    type: str
    value: str
    created_at: str


class StripConfigResponse(BaseModel):
    entries: list[StripConfigEntry]


class StripConfigCreateRequest(BaseModel):
    type: str   # "prefix" | "suffix"
    value: str


class StripSuggestion(BaseModel):
    type: str   # "prefix" | "suffix"
    value: str
    count: int


class StripSuggestionsResponse(BaseModel):
    suggestions: list[StripSuggestion]


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

@router.put("/description-rules/{label:path}", response_model=DescriptionRule)
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

@router.delete("/description-rules/{label:path}", response_model=RuleDeleteResponse)
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
    dismissed = store.get_dismissed_descriptions()

    with store._connect() as conn:
        rows = conn.execute(
            """SELECT COALESCE(stripped_description, description) as desc, COUNT(*) as c
               FROM transactions
               WHERE clean_description IS NULL
               GROUP BY COALESCE(stripped_description, description)
               ORDER BY c DESC"""
        ).fetchall()

    if not rows:
        return SuggestionsResponse(groups=[], uncovered_total=0)

    # uncovered_total counts only non-dismissed descriptions
    all_descs = [(r[0], r[1]) for r in rows]
    uncovered_total = sum(1 for d, _ in all_descs if d not in dismissed)

    # Filter out dismissed before grouping
    rows_filtered = [(d, c) for d, c in all_descs if d not in dismissed]
    if not rows_filtered:
        return SuggestionsResponse(groups=[], uncovered_total=uncovered_total)
    raw_to_canonical: dict[str, str] = {}
    raw_freq: dict[str, int] = {}
    for raw, count in rows_filtered:
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
        if len(members) == 1:
            # Single description: use it verbatim as the pattern (already stripped of
            # bank noise by the user's prefix/suffix config).  Escape regex metacharacters
            # so the pattern matches literally.
            raw = members[0]
            # Escape regex metacharacters but leave spaces unescaped
            common = [re.sub(r'(?=[\\^$*+?{}\[\]|().])', r'\\', raw)]
            label_text = _title_case(_normalize(raw)) or raw.title()
        else:
            common = _common_tokens(members)
            if not common:
                norm = _normalize(members[0]).split()
                common = [norm[0]] if norm else [members[0][:8]]
            label_text = _title_case(canonical)
        groups.append(SuggestionGroup(
            canonical=canonical,
            suggested_label=label_text,
            suggested_patterns=common,
            members=[{"raw": m, "count": raw_freq[m]} for m in sorted(members, key=lambda m: -raw_freq[m])],
            total_count=total_count,
        ))

    groups.sort(key=lambda g: -g.total_count)
    return SuggestionsResponse(groups=groups[:limit], uncovered_total=uncovered_total)


# ---------------------------------------------------------------------------
# POST /description-suggestions/dismiss  — permanently hide a suggestion
# ---------------------------------------------------------------------------

@router.post("/description-suggestions/dismiss", status_code=204)
def dismiss_suggestion(
    body: DismissRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """Permanently dismiss a description from suggestions. Survives reloads."""
    store.add_dismissed_description(body.description)


# ---------------------------------------------------------------------------
# POST /description-suggestions/mark-clean  — mark a description as already clean
# ---------------------------------------------------------------------------

@router.post("/description-suggestions/mark-clean", response_model=MarkCleanResponse)
def mark_clean(
    body: MarkCleanRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """
    Mark every transaction matching description as already clean.
    Stores the provided label as clean_description with source='clean'.
    Skips transactions already edited manually.
    """
    updated = store.mark_description_clean(body.description, body.label)
    return MarkCleanResponse(updated=updated, label=body.label)


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
            # Merge patterns: keep existing ones and append new ones not already present
            existing = shared.update_rule(rule.label)  # fetch without changes
            existing_patterns: list[str] = existing["patterns"] if existing else []
            merged = list(existing_patterns)
            for p in rule.patterns:
                if p not in merged:
                    merged.append(p)
            shared.update_rule(rule.label, patterns=merged)
        else:
            shared.create_rule(rule.label, rule.patterns, rule.position)
        saved += 1

    _reload_all()

    strip_config = store.get_strip_config()
    all_txs = store.get_all_descriptions()
    categorized = [categorize_transaction(tx, strip_config=strip_config) for tx in all_txs]
    updated = store.bulk_update_categories(categorized)

    return ApplyRulesResponse(saved=saved, updated=updated)


# ---------------------------------------------------------------------------
# GET /description-strip-config
# ---------------------------------------------------------------------------

@router.get("/description-strip-config", response_model=StripConfigResponse)
def get_strip_config(
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    entries = store.get_strip_config()
    return StripConfigResponse(
        entries=[StripConfigEntry(**e) for e in entries]
    )


# ---------------------------------------------------------------------------
# POST /description-strip-config
# ---------------------------------------------------------------------------

@router.post("/description-strip-config", response_model=StripConfigEntry, status_code=201)
def add_strip_entry(
    body: StripConfigCreateRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    if body.type not in ("prefix", "suffix"):
        raise HTTPException(status_code=422, detail="type must be 'prefix' or 'suffix'.")
    if not body.value.strip():
        raise HTTPException(status_code=422, detail="value cannot be empty.")
    try:
        entry = store.add_strip_entry(body.type, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return StripConfigEntry(**entry)


# ---------------------------------------------------------------------------
# DELETE /description-strip-config/{id}
# ---------------------------------------------------------------------------

@router.delete("/description-strip-config/{entry_id}")
def delete_strip_entry(
    entry_id: int,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    deleted = store.delete_strip_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Strip config entry {entry_id} not found.")
    return {"deleted": True, "id": entry_id}


# ---------------------------------------------------------------------------
# GET /description-strip-suggestions
# Suggests frequent leading/trailing tokens from raw descriptions (≥3 occurrences)
# ---------------------------------------------------------------------------

_STRIP_NOISE_TOKENS = {
    "DE", "A", "EN", "EL", "LA", "LOS", "LAS", "DEL", "AL", "Y",
    "ES", "COM", "NET", "S.L", "SL", "SA", "S.A",
}
_STRIP_NUMERIC_RE = re.compile(r"^\d+[\d\s\-\*\.]*$")
_STRIP_ALPHANUMERIC_RE = re.compile(r"^[A-Z0-9]{6,}$")


def _strip_tokenize(description: str) -> list[str]:
    """Split a raw description into normalised uppercase tokens."""
    upper = description.upper()
    nfkd = unicodedata.normalize("NFKD", upper)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return [t for t in re.split(r"[\s\-\*\.,/\\|]+", cleaned) if t]


def _is_noise_token(token: str) -> bool:
    return (
        len(token) < 3
        or token in _STRIP_NOISE_TOKENS
        or bool(_STRIP_NUMERIC_RE.match(token))
        or bool(_STRIP_ALPHANUMERIC_RE.match(token))
    )


@router.get("/description-strip-suggestions", response_model=StripSuggestionsResponse)
def get_strip_suggestions(
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT description FROM transactions"
        ).fetchall()

    descriptions = [r[0] for r in rows if r[0]]

    prefix_counts: dict[str, int] = defaultdict(int)
    suffix_counts: dict[str, int] = defaultdict(int)

    for desc in descriptions:
        tokens = _strip_tokenize(desc)
        if not tokens:
            continue
        first = tokens[0]
        last = tokens[-1]
        if not _is_noise_token(first):
            prefix_counts[first] += 1
        if not _is_noise_token(last) and last != first:
            suffix_counts[last] += 1

    min_count = 3
    suggestions: list[StripSuggestion] = []

    for value, count in sorted(prefix_counts.items(), key=lambda x: -x[1]):
        if count >= min_count:
            suggestions.append(StripSuggestion(type="prefix", value=value, count=count))

    for value, count in sorted(suffix_counts.items(), key=lambda x: -x[1]):
        if count >= min_count:
            suggestions.append(StripSuggestion(type="suffix", value=value, count=count))

    # Exclude tokens already configured
    existing = {(e["type"], e["value"].upper()) for e in store.get_strip_config()}
    suggestions = [
        s for s in suggestions
        if (s.type, s.value.upper()) not in existing
    ]

    return StripSuggestionsResponse(suggestions=suggestions)
