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


def normalize(raw: RawTransaction, bank_id: str) -> dict[str, Any]:
    """
    Returns a normalized transaction dict.

    Fields:
        id              — deterministic SHA-256 hash of (bank_id, date_op, description, amount)
        bank_id         — source bank identifier
        date            — ISO date string (date_operation)
        date_value      — ISO date string (date_value / effective date)
        description     — original description text
        amount          — signed float (negative = debit, positive = credit)
        balance         — running balance after this transaction
        currency        — ISO currency code
        transaction_type— detected type from YAML patterns
        is_reversal     — bool
        category        — None (filled later by categorizer)
        category_source — None (filled later: 'rule' | 'ai' | 'cache')
        month           — YYYY-MM string for grouping
        year            — int
    """
    tx_id = _make_id(bank_id, raw.date_operation, raw.description, raw.amount)

    return {
        "id": tx_id,
        "bank_id": bank_id,
        "date": raw.date_operation.isoformat(),
        "date_value": raw.date_value.isoformat(),
        "description": raw.description,
        "amount": round(raw.amount, 2),
        "balance": round(raw.balance, 2),
        "currency": raw.currency,
        "transaction_type": raw.transaction_type,
        "is_reversal": raw.is_reversal,
        "category": None,
        "category_source": None,
        "month": raw.date_operation.strftime("%Y-%m"),
        "year": raw.date_operation.year,
    }


def _make_id(bank_id: str, date_op: date, description: str, amount: float) -> str:
    """Deterministic ID so re-importing the same file doesn't create duplicates."""
    raw = f"{bank_id}|{date_op.isoformat()}|{description}|{amount:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
