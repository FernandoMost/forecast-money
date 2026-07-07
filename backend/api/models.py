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
    clean_description: str | None
    clean_description_source: str | None
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
    total: int          # total matching rows (unpaginated)
    amount_total: float # sum of amount for all matching rows (unpaginated)
    limit: int
    offset: int
    items: list[Transaction]


# ---------------------------------------------------------------------------
# Transaction patch (manual edit)
# ---------------------------------------------------------------------------

class PatchTransactionRequest(BaseModel):
    clean_description: str | None = None
    category: str | None = None
    subcategory: str | None = None


class PatchTransactionResponse(BaseModel):
    id: str
    clean_description: str | None
    clean_description_source: str | None
    category: str | None
    subcategory: str | None
    category_source: str | None


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


# ---------------------------------------------------------------------------
# Recategorize
# ---------------------------------------------------------------------------

class RecategorizeResponse(BaseModel):
    updated: int
    category_sources: dict[str, int]
    clean_description_sources: dict[str, int]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class MonthSummaryForDashboard(BaseModel):
    """Monthly summary enriched with dashboard-specific fields."""
    month: str
    tx_count: int
    total_income: float
    total_expenses: float
    net_savings: float
    drew_from_savings: bool
    savings_rate: float
    min_balance: float
    max_balance: float
    last_balance: float | None          # balance of the last transaction in this month
    last_balance_date: str | None       # date of that transaction (YYYY-MM-DD)
    leisure_spent: float                # restaurants + entertainment
    leisure_budget: float               # income * 20%
    leisure_remaining: float            # leisure_budget - leisure_spent
    days_of_data: int                   # span of dates with transactions
    first_date: str | None
    last_date: str | None
    # pace fields — only meaningful for partial (current) months
    days_elapsed: int | None = None     # calendar days elapsed in the month so far
    days_in_month: int | None = None    # total calendar days in the month
    projected_month_end_expenses: float | None = None
    by_category: list[CategoryBreakdown] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    last_transaction_date: str | None
    days_since_last_update: int         # calendar days between last_transaction_date and today
    # The month shown prominently — current month if ≥15 days of data, else last full month
    primary_month: MonthSummaryForDashboard
    # The other month shown in a compact secondary strip
    secondary_month: MonthSummaryForDashboard | None
    # True when primary_month is the current (partial) month
    primary_is_current: bool
    health: HealthScoreResponse
