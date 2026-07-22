"""
parser/normalizer.py

Converts RawTransaction objects (parser output) into normalized Transaction
dicts suitable for storage, analysis, and API responses.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from typing import Any

from parser.bank_parser import RawTransaction


def normalize(
    raw: RawTransaction,
    bank_id: str,
    strip_description_prefixes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Returns a normalized transaction dict.

    Fields:
        id              — deterministic SHA-256 hash of (bank_id, date_op, description, amount)
                          Always computed from the *original* description so re-imports are stable.
        bank_id         — source bank identifier
        date            — ISO date string (date_operation)
        date_value      — ISO date string (date_value / effective date)
        description     — description text after stripping configured prefixes (e.g. "PAGO MOVIL EN ")
        amount          — signed float (negative = debit, positive = credit)
        balance         — running balance after this transaction
        currency        — ISO currency code
        is_reversal     — bool
        category        — None (filled later by categorizer)
        category_source — None (filled later: 'rule' | 'ai' | 'cache')
        month           — YYYY-MM string for grouping
        year            — int

    Args:
        strip_description_prefixes: Optional list of case-insensitive prefixes to remove from the
            description before storing. The hash (id) is always computed from the raw description
            so that re-importing the same file never creates duplicates.
    """
    # ID uses the original description to ensure stable deduplication across re-imports.
    tx_id = _make_id(bank_id, raw.date_operation, raw.description, raw.amount)

    description = _strip_prefixes(raw.description, strip_description_prefixes or [])

    return {
        "id": tx_id,
        "bank_id": bank_id,
        "date": raw.date_operation.isoformat(),
        "date_value": raw.date_value.isoformat(),
        "description": description,
        "amount": round(raw.amount, 2),
        "balance": round(raw.balance, 2),
        "currency": raw.currency,
        "is_reversal": raw.is_reversal,
        "clean_description": None,
        "clean_description_source": None,
        "category": None,
        "category_source": None,
        "month": raw.date_operation.strftime("%Y-%m"),
        "year": raw.date_operation.year,
    }


def _make_id(bank_id: str, date_op: date, description: str, amount: float) -> str:
    """Deterministic ID so re-importing the same file doesn't create duplicates."""
    raw = f"{bank_id}|{date_op.isoformat()}|{description}|{amount:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _strip_prefixes(description: str, prefixes: list[str]) -> str:
    """Remove the first matching prefix (case-insensitive) from description.

    Only one prefix is stripped — the first one that matches.

    Examples:
        _strip_prefixes("PAGO MOVIL EN MERCADONA 0312", ["PAGO MOVIL EN "])
        → "MERCADONA 0312"

        _strip_prefixes("COMPRA ONLINE AMAZON", ["PAGO MOVIL EN "])
        → "COMPRA ONLINE AMAZON"  (no prefix matched — unchanged)
    """
    upper = description.upper()
    for prefix in prefixes:
        if upper.startswith(prefix.upper()):
            return description[len(prefix):]
    return description
