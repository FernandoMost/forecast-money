"""
api/routes.py — FastAPI route handlers.

Endpoints:
  POST   /upload                — Upload a bank statement xlsx/csv
  GET    /dashboard             — Dashboard: health score + current/last month enriched summaries
  GET    /summary/{month}       — Monthly financial summary
  GET    /transactions          — Paginated + filtered transaction list
  GET    /health-score          — Full 7-rule health analysis
  GET    /health                — API health check
  GET    /months                — Available months list
  DELETE /data                  — Wipe all transactions and imports
  POST   /recategorize          — Re-apply rules to all stored transactions
"""

from __future__ import annotations

import calendar
import tempfile
import uuid
from datetime import date as _date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from api.models import (
    DashboardResponse,
    HealthCheckResponse,
    HealthScoreResponse,
    MonthSummaryForDashboard,
    MonthlySummary,
    PatchTransactionRequest,
    PatchTransactionResponse,
    RecategorizeResponse,
    TransactionList,
    UploadResponse,
)
from api.deps import get_store, get_settings
from categorizer.ai_categorizer import AiCategorizer
from categorizer.rule_categorizer import categorize_transaction, reload_rules as reload_category_rules
from categorizer.description_cleaner import reload_rules as reload_clean_rules
from db.sqlite_store import SqliteStore
from parser.bank_parser import BankParser
from parser.normalizer import normalize
from rules.health_engine import HealthEngine

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=UploadResponse, summary="Upload a bank statement Excel file")
async def upload_statement(
    file: UploadFile = File(..., description="Bank statement .xlsx or .csv export"),
    bank: str = Form(default="santander", description="Bank config name (without .yaml)"),
    use_ai: bool = Form(default=False, description="Use Ollama AI categorizer"),
    settings=Depends(get_settings),
    store: SqliteStore = Depends(get_store),
):
    fname = file.filename or ""
    if not fname.endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are accepted.")

    banks_dir = Path(__file__).parent.parent.parent / "banks"
    bank_config = banks_dir / f"{bank}.yaml"
    if not bank_config.exists():
        raise HTTPException(status_code=400, detail=f"Unknown bank config: '{bank}'. Available: {[p.stem for p in banks_dir.glob('*.yaml')]}")

    suffix = ".csv" if fname.endswith(".csv") else ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        parser = BankParser(bank_config)
        result = parser.parse(tmp_path)
        meta = result.metadata

        normalized = [normalize(raw, meta.bank_id) for raw in result.transactions]

        if use_ai:
            ai = AiCategorizer(cache_path=settings.data_dir / "category_cache.db")
            categorized = [ai.categorize_transaction(tx) for tx in normalized]
        else:
            categorized = [categorize_transaction(tx) for tx in normalized]

        import_id = uuid.uuid4().hex
        inserted = store.upsert_transactions(categorized, import_id)
        store.save_import(
            import_id=import_id,
            bank_id=meta.bank_id,
            filename=file.filename,
            tx_count=inserted,
            metadata={
                "account_number": meta.account_number,
                "account_holder": meta.account_holder,
                "current_balance": meta.current_balance,
                "export_date": meta.export_date,
            },
        )

        return UploadResponse(
            import_id=import_id,
            bank_id=meta.bank_id,
            filename=file.filename,
            transactions_imported=inserted,
            parse_warnings=result.parse_warnings,
            metadata={
                "account_number": meta.account_number,
                "account_holder": meta.account_holder,
                "current_balance": meta.current_balance,
                "export_date": meta.export_date,
            },
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

def _build_month_summary(raw: dict, today: _date) -> MonthSummaryForDashboard:
    """
    Enriches a get_dashboard_month_summary() dict with leisure budget and
    pace/projection fields (only meaningful for the current partial month).
    """
    income = raw["total_income"]
    leisure_budget = round(income * 0.20, 2)
    leisure_spent = raw["leisure_spent"]
    leisure_remaining = round(leisure_budget - leisure_spent, 2)

    # Pace fields — only computed when month matches the current calendar month
    month_str = raw["month"]           # YYYY-MM
    days_elapsed: int | None = None
    days_in_month: int | None = None
    projected: float | None = None

    year, mo = int(month_str[:4]), int(month_str[5:7])
    if year == today.year and mo == today.month:
        days_elapsed = today.day
        days_in_month = calendar.monthrange(year, mo)[1]
        days_of_data = raw["days_of_data"]
        if days_of_data > 0 and raw["total_expenses"] > 0:
            projected = round(raw["total_expenses"] / days_of_data * days_in_month, 2)

    return MonthSummaryForDashboard(
        **{k: v for k, v in raw.items() if k not in ("leisure_budget", "leisure_remaining")},
        leisure_budget=leisure_budget,
        leisure_remaining=leisure_remaining,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        projected_month_end_expenses=projected,
    )


@router.get("/dashboard", response_model=DashboardResponse, summary="Dashboard snapshot")
def get_dashboard(store: SqliteStore = Depends(get_store)):
    """
    Single endpoint for the dashboard page.
    Returns health score + enriched monthly summaries + staleness info.

    Primary/secondary month logic:
      - If the current calendar month has ≥15 days of transaction data → primary = current month
      - Otherwise → primary = last full month, secondary = current partial month
    """
    all_txs = store.get_all_transactions_for_rules()
    if not all_txs:
        raise HTTPException(status_code=404, detail="No transactions found. Upload a statement first.")

    # --- Health score ---
    sorted_txs = sorted(all_txs, key=lambda t: t["date"], reverse=True)
    latest_balance = sorted_txs[0].get("balance")
    engine = HealthEngine(current_balance=latest_balance)
    health = engine.analyze(all_txs)
    health_response = HealthScoreResponse(
        overall_score=health.overall_score,
        grade=health.grade,
        months_analyzed=health.months_analyzed,
        summary=health.summary,
        rules=[
            {"rule_id": r.rule_id, "name": r.name, "status": r.status,
             "score": r.score, "message": r.message, "details": r.details}
            for r in health.rules
        ],
        alerts=[
            {"rule_id": r.rule_id, "name": r.name, "status": r.status, "message": r.message}
            for r in health.alerts
        ],
    )

    # --- Staleness ---
    last_tx_date_str = store.get_latest_transaction_date()
    today = _date.today()
    days_since = 0
    if last_tx_date_str:
        last_tx_date = _date.fromisoformat(last_tx_date_str)
        days_since = (today - last_tx_date).days

    # --- Available months ---
    available_months = store.get_available_months()   # DESC order
    current_month_str = today.strftime("%Y-%m")

    # --- Current month data (may be empty) ---
    current_raw = (
        store.get_dashboard_month_summary(current_month_str)
        if current_month_str in available_months
        else None
    )

    # --- Last full month (most recent month that is not the current calendar month) ---
    last_full_month_str = next(
        (m for m in available_months if m != current_month_str), None
    )
    last_full_raw = (
        store.get_dashboard_month_summary(last_full_month_str)
        if last_full_month_str
        else None
    )

    # --- Primary / secondary decision ---
    current_days_of_data = current_raw["days_of_data"] if current_raw else 0
    primary_is_current = current_days_of_data >= 15

    if primary_is_current:
        primary_raw = current_raw
        secondary_raw = last_full_raw
    else:
        primary_raw = last_full_raw
        secondary_raw = current_raw

    if primary_raw is None:
        raise HTTPException(status_code=404, detail="No monthly data available.")

    primary = _build_month_summary(primary_raw, today)
    secondary = _build_month_summary(secondary_raw, today) if secondary_raw else None

    return DashboardResponse(
        last_transaction_date=last_tx_date_str,
        days_since_last_update=days_since,
        primary_month=primary,
        secondary_month=secondary,
        primary_is_current=primary_is_current,
        health=health_response,
    )


# ---------------------------------------------------------------------------
# GET /summary/{month}
# ---------------------------------------------------------------------------

@router.get("/summary/{month}", response_model=MonthlySummary, summary="Monthly financial summary")
def get_monthly_summary(
    month: str,
    store: SqliteStore = Depends(get_store),
):
    """Returns income, expenses, savings, and category breakdown for a given month (YYYY-MM)."""
    available = store.get_available_months()
    if month not in available:
        raise HTTPException(
            status_code=404,
            detail=f"No data for month '{month}'. Available: {available}",
        )
    data = store.get_monthly_summary(month)
    return MonthlySummary(**data)


# ---------------------------------------------------------------------------
# GET /transactions
# ---------------------------------------------------------------------------

@router.get("/transactions", response_model=TransactionList, summary="List transactions")
def list_transactions(
    month: str | None = Query(None, description="Filter by month (YYYY-MM)"),
    year: int | None = Query(None, description="Filter by year (ignored when month is set)"),
    category: str | None = Query(None, description="Filter by category"),
    subcategory: str | None = Query(None, description="Filter by subcategory"),
    bank_id: str | None = Query(None, description="Filter by bank"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store: SqliteStore = Depends(get_store),
):
    result = store.get_transactions(
        month=month, year=year, category=category, subcategory=subcategory,
        bank_id=bank_id, limit=limit, offset=offset,
    )
    for item in result["items"]:
        item["is_reversal"] = bool(item.get("is_reversal"))

    return TransactionList(
        total=result["total"],
        amount_total=result["amount_total"],
        limit=limit,
        offset=offset,
        items=result["items"],
    )


# ---------------------------------------------------------------------------
# PATCH /transactions/{id}
# ---------------------------------------------------------------------------

@router.patch("/transactions/{tx_id}", response_model=PatchTransactionResponse, summary="Manually edit a transaction")
def patch_transaction(
    tx_id: str,
    body: PatchTransactionRequest,
    store: SqliteStore = Depends(get_store),
):
    """
    Override clean_description and/or category/subcategory for a single transaction.
    Sets category_source and/or clean_description_source to 'manual'.
    Only the provided fields are updated; omitted fields are left unchanged.
    """
    updated = store.update_transaction_manual(
        tx_id=tx_id,
        clean_description=body.clean_description,
        category=body.category,
        subcategory=body.subcategory,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found.")

    tx = store.get_transaction_by_id(tx_id)
    return PatchTransactionResponse(
        id=tx["id"],
        clean_description=tx["clean_description"],
        clean_description_source=tx["clean_description_source"],
        category=tx["category"],
        subcategory=tx["subcategory"],
        category_source=tx["category_source"],
    )


# ---------------------------------------------------------------------------
# GET /health-score
# ---------------------------------------------------------------------------

@router.get("/health-score", response_model=HealthScoreResponse, summary="Financial health score (0-100)")
def get_health_score(
    store: SqliteStore = Depends(get_store),
):
    """Runs all 7 financial health rules against stored transactions and returns a score + alerts."""
    all_txs = store.get_all_transactions_for_rules()
    if not all_txs:
        raise HTTPException(status_code=404, detail="No transactions found. Upload a statement first.")

    # Get latest known balance from most recent transaction
    latest_balance = None
    if all_txs:
        sorted_txs = sorted(all_txs, key=lambda t: t["date"], reverse=True)
        latest_balance = sorted_txs[0].get("balance")

    engine = HealthEngine(current_balance=latest_balance)
    health = engine.analyze(all_txs)

    return HealthScoreResponse(
        overall_score=health.overall_score,
        grade=health.grade,
        months_analyzed=health.months_analyzed,
        summary=health.summary,
        rules=[
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "status": r.status,
                "score": r.score,
                "message": r.message,
                "details": r.details,
            }
            for r in health.rules
        ],
        alerts=[
            {"rule_id": r.rule_id, "name": r.name, "status": r.status, "message": r.message}
            for r in health.alerts
        ],
    )


# ---------------------------------------------------------------------------
# GET /months
# ---------------------------------------------------------------------------

@router.get("/months", summary="List available months with data")
def list_months(store: SqliteStore = Depends(get_store)):
    return {"months": store.get_available_months()}


# ---------------------------------------------------------------------------
# GET /health  (API health check)
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthCheckResponse, summary="API health check")
def health_check(
    settings=Depends(get_settings),
    store: SqliteStore = Depends(get_store),
):
    months = store.get_available_months()
    txs = store.get_transactions(limit=1)
    total = len(store.get_all_transactions_for_rules())
    return HealthCheckResponse(
        status="ok",
        version="1.0.0",
        db_path=str(settings.db_path),
        available_months=months,
        total_transactions=total,
    )


# ---------------------------------------------------------------------------
# DELETE /data
# ---------------------------------------------------------------------------

@router.delete("/data", summary="Wipe all transactions and imports")
def clear_data(store: SqliteStore = Depends(get_store)):
    """Deletes all stored transactions and import records. Irreversible."""
    result = store.clear_all()
    return {"status": "cleared", **result}


# ---------------------------------------------------------------------------
# POST /recategorize
# ---------------------------------------------------------------------------

@router.post("/recategorize", response_model=RecategorizeResponse, summary="Re-apply rules to all stored transactions")
def recategorize(
    use_ai: bool = Query(False, description="Use Ollama AI for transactions that rules don't match"),
    settings=Depends(get_settings),
    store: SqliteStore = Depends(get_store),
):
    """
    Reloads rules from YAML config files and re-applies them to every stored transaction.
    Useful after editing category_rules.yaml or clean_description_rules.yaml.
    Pass use_ai=true to also run Ollama for unmatched descriptions.
    """
    # Reload rules from disk so edits take effect without restarting the server
    reload_category_rules()
    reload_clean_rules()

    rows = store.get_all_descriptions()
    if not rows:
        return RecategorizeResponse(updated=0, category_sources={}, clean_description_sources={})

    if use_ai:
        ai = AiCategorizer(
            ollama_url=settings.ollama_url,
            model=settings.ollama_model,
            cache_path=settings.data_dir / "category_cache.db",
        )
        categorized = [ai.categorize_transaction(row) for row in rows]
    else:
        categorized = [categorize_transaction(row) for row in rows]

    updated = store.bulk_update_categories(categorized)

    cat_sources: dict[str, int] = {}
    clean_sources: dict[str, int] = {}
    for tx in categorized:
        cs = tx.get("category_source") or "unknown"
        cat_sources[cs] = cat_sources.get(cs, 0) + 1
        ds = tx.get("clean_description_source") or "none"
        clean_sources[ds] = clean_sources.get(ds, 0) + 1

    return RecategorizeResponse(
        updated=updated,
        category_sources=cat_sources,
        clean_description_sources=clean_sources,
    )
