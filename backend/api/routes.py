"""
api/routes.py — FastAPI route handlers.

Endpoints:
  POST   /upload                — Upload a bank statement xlsx/csv
  GET    /imports               — List all import records
  DELETE /imports/{import_id}   — Delete a single import and its transactions
  GET    /dashboard             — Dashboard: health score + current/last month enriched summaries
  GET    /summary/{month}       — Monthly financial summary
  GET    /transactions          — Paginated + filtered transaction list
  PATCH  /transactions/{id}     — Manually edit a transaction
  GET    /categories            — List full category tree
  POST   /categories            — Create a new category or subcategory
  PATCH  /categories/{id}       — Update a category (name, color, role, position)
  DELETE /categories/{id}       — Delete a category (nulls associated transactions)
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
    CategoryCreateRequest,
    CategoryDeleteResponse,
    CategoryItem,
    CategoryListResponse,
    CategoryUpdateRequest,
    CategoryWithChildren,
    DashboardResponse,
    DeleteImportResponse,
    HealthCheckResponse,
    HealthScoreHistoryResponse,
    HealthScoreResponse,
    ImportListResponse,
    MonthSummaryForDashboard,
    MonthlySummary,
    PatchTransactionRequest,
    PatchTransactionResponse,
    RecategorizeResponse,
    TransactionList,
    UploadResponse,
)
from api.deps import get_store, get_settings, get_current_user
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

        strip_prefixes = parser.strip_description_prefixes
        strip_config = store.get_strip_config()
        normalized = [normalize(raw, meta.bank_id, strip_prefixes) for raw in result.transactions]

        if use_ai:
            ai = AiCategorizer(cache_path=settings.data_dir / "category_cache.db", store=store)
            categorized = [ai.categorize_transaction(tx, strip_config=strip_config) for tx in normalized]
        else:
            categorized = [categorize_transaction(tx, strip_config=strip_config) for tx in normalized]

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

        # Save health score snapshot whenever new transactions were inserted
        if inserted > 0:
            try:
                all_txs_for_health = store.get_all_transactions_for_rules()
                sorted_h = sorted(all_txs_for_health, key=lambda t: t["date"], reverse=True)
                h_balance = sorted_h[0].get("balance") if sorted_h else None
                h_engine = HealthEngine(current_balance=h_balance, store=store)
                h_report = h_engine.analyze(all_txs_for_health)
                store.save_health_score(
                    import_id=import_id,
                    overall_score=h_report.overall_score,
                    grade=h_report.grade,
                    rule_scores={r.rule_id: r.score for r in h_report.rules},
                )
            except Exception:
                pass  # non-critical — never block the upload response

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
# GET /imports  |  DELETE /imports/{import_id}
# ---------------------------------------------------------------------------

@router.get("/imports", response_model=ImportListResponse, summary="List all import records")
def list_imports(store: SqliteStore = Depends(get_store)):
    """Returns all import records ordered by most recent first, including metadata."""
    return ImportListResponse(imports=store.list_imports())


@router.delete("/imports/{import_id}", response_model=DeleteImportResponse, summary="Delete a single import and its transactions")
def delete_import(import_id: str, store: SqliteStore = Depends(get_store)):
    """
    Deletes the import record and all transactions associated with it.
    Also removes any health score history snapshot linked to this import.
    This action is irreversible.
    """
    imports = store.list_imports()
    if not any(i["id"] == import_id for i in imports):
        raise HTTPException(status_code=404, detail=f"Import '{import_id}' not found.")
    result = store.delete_import(import_id)
    return DeleteImportResponse(
        status="deleted",
        import_id=import_id,
        deleted_transactions=result["deleted_transactions"],
    )


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
    engine = HealthEngine(current_balance=latest_balance, store=store)
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
            {"rule_id": r.rule_id, "name": r.name, "status": r.status, "message": r.message, "details": r.details}
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

    latest_balance = store.get_latest_balance()

    return DashboardResponse(
        last_transaction_date=last_tx_date_str,
        days_since_last_update=days_since,
        current_balance=latest_balance["balance"],
        current_balance_date=latest_balance["date"],
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
    clean_description: str | None = Query(None, description="Filter by exact clean_description (rule label)"),
    sort_by: str = Query("date", description="Column to sort by: date|amount|balance|description|category|month"),
    sort_dir: str = Query("desc", description="Sort direction: asc|desc"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store: SqliteStore = Depends(get_store),
):
    result = store.get_transactions(
        month=month, year=year, category=category, subcategory=subcategory,
        bank_id=bank_id, clean_description=clean_description,
        sort_by=sort_by, sort_dir=sort_dir,
        limit=limit, offset=offset,
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
    Override clean_description, category/subcategory and/or month for a single transaction.
    When month (YYYY-MM) is provided, date is set to the 1st of that month.
    Sets category_source and/or clean_description_source to 'manual'.
    Only the provided fields are updated; omitted fields are left unchanged.
    """
    if body.month is not None:
        import re as _re
        if not _re.match(r"^\d{4}-\d{2}$", body.month):
            raise HTTPException(status_code=422, detail="month must be in YYYY-MM format.")

    updated = store.update_transaction_manual(
        tx_id=tx_id,
        clean_description=body.clean_description,
        category=body.category,
        subcategory=body.subcategory,
        month=body.month,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found.")

    tx = store.get_transaction_by_id(tx_id)
    return PatchTransactionResponse(
        id=tx["id"],
        date=tx["date"],
        month=tx["month"],
        year=tx["year"],
        clean_description=tx["clean_description"],
        clean_description_source=tx["clean_description_source"],
        category=tx["category"],
        subcategory=tx["subcategory"],
        category_source=tx["category_source"],
    )


# ---------------------------------------------------------------------------
# GET /categories
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=CategoryListResponse, summary="List category tree")
def list_categories(store: SqliteStore = Depends(get_store)):
    """
    Returns the full category tree: top-level categories with their subcategories nested.
    """
    flat = store.get_categories()
    # Build tree: top-level first, then attach children
    top_level = [c for c in flat if c["parent_id"] is None]
    children_by_parent: dict[str, list[dict]] = {}
    for c in flat:
        if c["parent_id"] is not None:
            children_by_parent.setdefault(c["parent_id"], []).append(c)

    result = []
    for cat in top_level:
        subs = sorted(children_by_parent.get(cat["id"], []), key=lambda x: x["position"])
        result.append(CategoryWithChildren(
            id=cat["id"],
            name=cat["name"],
            color=cat["color"],
            role=cat["role"],
            position=cat["position"],
            created_at=cat.get("created_at"),
            subcategories=[CategoryItem(**s) for s in subs],
        ))

    return CategoryListResponse(categories=sorted(result, key=lambda x: x.position))


# ---------------------------------------------------------------------------
# POST /categories
# ---------------------------------------------------------------------------

@router.post("/categories", response_model=CategoryItem, status_code=201, summary="Create a category or subcategory")
def create_category(
    body: CategoryCreateRequest,
    store: SqliteStore = Depends(get_store),
):
    """
    Create a new top-level category (parent_id=null) or subcategory (parent_id=existing category id).
    The id must be a unique slug (e.g. 'transport', 'fuel').
    """
    # Validate parent exists if provided
    if body.parent_id is not None:
        parent = store.get_category_by_id(body.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail=f"Parent category '{body.parent_id}' not found.")
        if parent["parent_id"] is not None:
            raise HTTPException(status_code=400, detail="Subcategories cannot have subcategories (max depth: 2).")

    try:
        cat = store.create_category(
            cat_id=body.id,
            name=body.name,
            parent_id=body.parent_id,
            color=body.color,
            role=body.role,
            position=body.position,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return CategoryItem(**cat)


# ---------------------------------------------------------------------------
# PATCH /categories/{id}
# ---------------------------------------------------------------------------

@router.patch("/categories/{cat_id}", response_model=CategoryItem, summary="Update a category")
def patch_category(
    cat_id: str,
    body: CategoryUpdateRequest,
    store: SqliteStore = Depends(get_store),
):
    """
    Update name, color, role, and/or position of an existing category.
    Only the provided fields are changed.
    """
    updated = store.update_category(
        cat_id=cat_id,
        name=body.name,
        color=body.color,
        role=body.role,
        position=body.position,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Category '{cat_id}' not found.")
    return CategoryItem(**updated)


# ---------------------------------------------------------------------------
# DELETE /categories/{id}
# ---------------------------------------------------------------------------

@router.delete("/categories/{cat_id}", response_model=CategoryDeleteResponse, summary="Delete a category")
def delete_category(
    cat_id: str,
    store: SqliteStore = Depends(get_store),
):
    """
    Delete a category (and its subcategories).
    Transactions referencing the deleted category/subcategories will have their
    category and subcategory set to NULL.
    """
    existing = store.get_category_by_id(cat_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Category '{cat_id}' not found.")

    result = store.delete_category(cat_id)
    return CategoryDeleteResponse(**result)


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

    engine = HealthEngine(current_balance=latest_balance, store=store)
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
            {"rule_id": r.rule_id, "name": r.name, "status": r.status, "message": r.message, "details": r.details}
            for r in health.alerts
        ],
    )


# ---------------------------------------------------------------------------
# GET /health-history
# ---------------------------------------------------------------------------

@router.get("/health-history", response_model=HealthScoreHistoryResponse, summary="Health score history")
def get_health_history(
    limit: int = 50,
    store: SqliteStore = Depends(get_store),
):
    """Returns the historical health score snapshots recorded after each import."""
    history = store.get_health_score_history(limit=limit)
    return HealthScoreHistoryResponse(history=history)


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
        db_path=str(settings.users_data_dir),
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

    strip_config = store.get_strip_config()
    rows = store.get_all_descriptions()
    if not rows:
        return RecategorizeResponse(updated=0, category_sources={}, clean_description_sources={})

    if use_ai:
        ai = AiCategorizer(
            ollama_url=settings.ollama_url,
            model=settings.ollama_model,
            cache_path=settings.data_dir / "category_cache.db",
            store=store,
        )
        categorized = [ai.categorize_transaction(row, strip_config=strip_config) for row in rows]
    else:
        categorized = [categorize_transaction(row, strip_config=strip_config) for row in rows]

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
