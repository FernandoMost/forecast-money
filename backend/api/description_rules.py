"""
api/description_rules.py — CRUD for clean_description_rules.yaml + suggestion engine.

Endpoints:
  GET    /description-rules                — list all rules (with match counts)
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
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_store, get_current_user
from categorizer.description_cleaner import reload_rules as reload_clean_rules
from categorizer.rule_categorizer import reload_rules as reload_category_rules
from categorizer.rule_categorizer import categorize_transaction
from db.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DescriptionRule(BaseModel):
    label: str
    patterns: list[str]
    match_count: int = 0          # filled on GET, ignored on write


class RuleListResponse(BaseModel):
    rules: list[DescriptionRule]
    total: int


class RuleCreateRequest(BaseModel):
    label: str
    patterns: list[str]
    position: int | None = None   # None = append at end; 0 = prepend


class RuleUpdateRequest(BaseModel):
    new_label: str | None = None
    patterns: list[str] | None = None


class RuleDeleteResponse(BaseModel):
    deleted: bool
    label: str


class SuggestionGroup(BaseModel):
    canonical: str                  # normalized key used for grouping
    suggested_label: str            # Title Case of canonical
    suggested_patterns: list[str]   # tokens present in ALL members of the group
    members: list[dict]             # [{raw: str, count: int}]
    total_count: int


class SuggestionsResponse(BaseModel):
    groups: list[SuggestionGroup]
    uncovered_total: int            # total distinct raw descriptions with no clean_description


class ApplyRulesRequest(BaseModel):
    rules: list[RuleCreateRequest]  # one or more rules to save before recategorize


class ApplyRulesResponse(BaseModel):
    saved: int
    updated: int                    # rows updated by recategorize


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "clean_description_rules.yaml",
        Path(__file__).parent.parent / "config" / "clean_description_rules.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    # fallback: create in repo root config/
    p = candidates[0]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_yaml() -> list[dict]:
    path = _config_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _write_yaml(rules: list[dict]) -> None:
    path = _config_path()
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(rules, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _reload_all() -> None:
    reload_clean_rules()
    reload_category_rules()


# ---------------------------------------------------------------------------
# Match-count helper
# ---------------------------------------------------------------------------

def _count_matches(store: SqliteStore) -> dict[str, int]:
    """Return {label: count} for all transactions with a clean_description (by rule)."""
    with store._connect() as conn:
        rows = conn.execute(
            """SELECT clean_description, COUNT(*) as c
               FROM transactions
               WHERE clean_description IS NOT NULL
               GROUP BY clean_description"""
        ).fetchall()
    return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# GET /description-rules
# ---------------------------------------------------------------------------

@router.get("/description-rules", response_model=RuleListResponse)
def list_rules(
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    raw = _read_yaml()
    counts = _count_matches(store)
    rules = [
        DescriptionRule(
            label=entry["label"],
            patterns=entry.get("patterns", []),
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
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    raw = _read_yaml()
    if any(e["label"] == body.label for e in raw):
        raise HTTPException(status_code=409, detail=f"Rule '{body.label}' already exists.")
    if not body.patterns:
        raise HTTPException(status_code=422, detail="At least one pattern is required.")

    new_entry = {"label": body.label, "patterns": body.patterns}
    if body.position is None:
        raw.append(new_entry)
    else:
        raw.insert(body.position, new_entry)

    _write_yaml(raw)
    _reload_all()
    return DescriptionRule(label=body.label, patterns=body.patterns, match_count=0)


# ---------------------------------------------------------------------------
# PUT /description-rules/{label}
# ---------------------------------------------------------------------------

@router.put("/description-rules/{label}", response_model=DescriptionRule)
def update_rule(
    label: str,
    body: RuleUpdateRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    raw = _read_yaml()
    idx = next((i for i, e in enumerate(raw) if e["label"] == label), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Rule '{label}' not found.")

    if body.new_label and body.new_label != label:
        if any(e["label"] == body.new_label for e in raw):
            raise HTTPException(status_code=409, detail=f"Rule '{body.new_label}' already exists.")
        raw[idx]["label"] = body.new_label

    if body.patterns is not None:
        if not body.patterns:
            raise HTTPException(status_code=422, detail="At least one pattern is required.")
        raw[idx]["patterns"] = body.patterns

    _write_yaml(raw)
    _reload_all()

    final_label = raw[idx]["label"]
    counts = _count_matches(store)
    return DescriptionRule(
        label=final_label,
        patterns=raw[idx]["patterns"],
        match_count=counts.get(final_label, 0),
    )


# ---------------------------------------------------------------------------
# DELETE /description-rules/{label}
# ---------------------------------------------------------------------------

@router.delete("/description-rules/{label}", response_model=RuleDeleteResponse)
def delete_rule(
    label: str,
    _user=Depends(get_current_user),
):
    raw = _read_yaml()
    original_len = len(raw)
    raw = [e for e in raw if e["label"] != label]
    if len(raw) == original_len:
        raise HTTPException(status_code=404, detail=f"Rule '{label}' not found.")
    _write_yaml(raw)
    _reload_all()
    return RuleDeleteResponse(deleted=True, label=label)


# ---------------------------------------------------------------------------
# Suggestion engine
# ---------------------------------------------------------------------------

# Words / tokens to strip before comparing — generic bank noise
_NOISE_TOKENS = {
    "COMPRA", "PAGO", "CARGO", "ABONO", "INGRESO", "TRANSFERENCIA",
    "INMEDIATA", "RECIBO", "LIQUIDACION", "COMISION", "CUOTA",
    "TPV", "POS", "OPE", "BIZUM", "SEPA", "DE", "A", "EN", "EL",
    "LA", "LOS", "LAS", "DEL", "AL", "Y", "S.L", "SL", "SA", "S.A",
    "ES", "COM", "NET", "WWW", "HTTP", "HTTPS",
}

# Regex for tokens that are pure noise regardless of content
_NOISE_PATTERNS = [
    re.compile(r"^\d+$"),                       # pure numbers
    re.compile(r"^[A-Z0-9]{6,}$"),              # long alphanumeric codes (IDs, refs)
    re.compile(r"^\d{1,2}[/\-]\d{1,2}([/\-]\d{2,4})?$"),  # dates
    re.compile(r"^\*+$"),                        # asterisks
]


def _normalize(description: str) -> str:
    """
    Normalise a raw bank description to a canonical grouping key.
    Steps: uppercase → remove accents → strip noise tokens → rejoin.
    Returns a space-joined string of meaningful tokens (may be empty).
    """
    # uppercase + remove accents
    upper = description.upper()
    nfkd = unicodedata.normalize("NFKD", upper)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))

    # split on whitespace and common separators
    tokens = re.split(r"[\s\-\*\.,/\\|]+", cleaned)

    significant = []
    for tok in tokens:
        if not tok:
            continue
        if tok in _NOISE_TOKENS:
            continue
        if any(p.match(tok) for p in _NOISE_PATTERNS):
            continue
        significant.append(tok)

    return " ".join(significant)


def _title_case(canonical: str) -> str:
    """Convert canonical ALL-CAPS key to Title Case label."""
    return " ".join(w.capitalize() for w in canonical.split())


def _common_tokens(descriptions: list[str]) -> list[str]:
    """
    Return the tokens that appear in ALL raw descriptions of the group —
    after normalisation. These form the minimal safe regex pattern.
    """
    if not descriptions:
        return []

    token_sets = [set(_normalize(d).split()) for d in descriptions]
    common = token_sets[0]
    for s in token_sets[1:]:
        common &= s

    # keep only tokens with 3+ chars (too-short tokens over-match)
    return sorted(t for t in common if len(t) >= 3)


def _prefix_key(canonical: str, min_len: int = 4) -> str:
    """Return the first token if it has >= min_len chars, else the full canonical."""
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
    """
    Returns groups of raw descriptions that have no clean_description,
    ordered by frequency (highest impact first).
    Each group has a suggested label (Title Case) and suggested regex patterns.
    """
    # 1. Fetch all uncleaned descriptions from DB
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

    # 2. Normalise and build raw→canonical map + frequency map
    raw_to_canonical: dict[str, str] = {}
    raw_freq: dict[str, int] = {}
    for raw, count in rows:
        canonical = _normalize(raw)
        raw_to_canonical[raw] = canonical if canonical else raw.upper()
        raw_freq[raw] = count

    # 3. Group by canonical (exact match pass)
    canonical_groups: dict[str, list[str]] = defaultdict(list)
    for raw, canonical in raw_to_canonical.items():
        canonical_groups[canonical].append(raw)

    # 4. Merge by prefix (second pass) — fuse groups sharing first significant token
    prefix_map: dict[str, str] = {}   # prefix → representative canonical
    merged: dict[str, list[str]] = defaultdict(list)

    for canonical, members in canonical_groups.items():
        prefix = _prefix_key(canonical)
        if prefix in prefix_map:
            # merge into the existing group using its representative
            rep = prefix_map[prefix]
            merged[rep].extend(members)
        else:
            prefix_map[prefix] = canonical
            merged[canonical].extend(members)

    # 5. Build SuggestionGroup objects, sort by total_count desc
    groups: list[SuggestionGroup] = []
    for canonical, members in merged.items():
        total_count = sum(raw_freq[m] for m in members)
        common = _common_tokens(members)
        suggested_patterns = common if common else [_normalize(members[0]).split()[0]] if _normalize(members[0]) else [members[0][:8]]
        groups.append(SuggestionGroup(
            canonical=canonical,
            suggested_label=_title_case(canonical),
            suggested_patterns=suggested_patterns,
            members=[{"raw": m, "count": raw_freq[m]} for m in sorted(members, key=lambda m: -raw_freq[m])],
            total_count=total_count,
        ))

    groups.sort(key=lambda g: -g.total_count)

    return SuggestionsResponse(
        groups=groups[:limit],
        uncovered_total=uncovered_total,
    )


# ---------------------------------------------------------------------------
# POST /description-rules/apply  — save rules + recategorize in one call
# ---------------------------------------------------------------------------

@router.post("/description-rules/apply", response_model=ApplyRulesResponse)
def apply_rules(
    body: ApplyRulesRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """
    Save one or more new rules to the YAML and immediately re-apply all rules
    to every transaction. Manual edits are preserved.
    """
    raw = _read_yaml()
    saved = 0
    for rule in body.rules:
        if not rule.patterns:
            continue
        if any(e["label"] == rule.label for e in raw):
            # update existing patterns instead of duplicating
            for e in raw:
                if e["label"] == rule.label:
                    e["patterns"] = rule.patterns
        else:
            entry = {"label": rule.label, "patterns": rule.patterns}
            if rule.position is None:
                raw.append(entry)
            else:
                raw.insert(rule.position, entry)
        saved += 1

    _write_yaml(raw)
    _reload_all()

    # Re-apply rules to all transactions (respects manual preservation in bulk_update)
    all_txs = store.get_all_descriptions()
    categorized = [categorize_transaction(tx) for tx in all_txs]
    updated = store.bulk_update_categories(categorized)

    return ApplyRulesResponse(saved=saved, updated=updated)
