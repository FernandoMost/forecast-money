"""
api/models.py — Pydantic request/response models for the FastAPI layer.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class CategoryBreakdown(BaseModel):
    category: str
    total: float
    count: int


class MonthlySummary(BaseModel):
    month: str
    tx_count: int
    total_income: float
    total_expenses: float
    net_savings: float
    savings_rate: float
    min_balance: float
    max_balance: float
    by_category: list[CategoryBreakdown]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    import_id: str
    bank_id: str
    filename: str
    transactions_imported: int
    parse_warnings: list[str]
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class Transaction(BaseModel):
    id: str
    bank_id: str
    date: str
    date_value: str
    description: str
    amount: float
    balance: float
    currency: str
    is_reversal: bool
    category: str | None
    subcategory: str | None
    category_source: str | None
    month: str
    year: int


class TransactionList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Transaction]


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

class RuleResultModel(BaseModel):
    rule_id: str
    name: str
    status: str          # green | amber | red
    score: float
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class AlertModel(BaseModel):
    rule_id: str
    name: str
    status: str
    message: str


class HealthScoreResponse(BaseModel):
    overall_score: float
    grade: str
    months_analyzed: list[str]
    summary: dict[str, Any]
    rules: list[RuleResultModel]
    alerts: list[AlertModel]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthCheckResponse(BaseModel):
    status: str
    version: str
    db_path: str
    available_months: list[str]
    total_transactions: int
