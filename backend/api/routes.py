"""
api/routes.py — FastAPI route handlers.

Endpoints:
  POST   /upload                — Upload a bank statement xlsx
  GET    /summary/{month}       — Monthly financial summary
  GET    /transactions          — Paginated + filtered transaction list
  GET    /health-score          — Full 7-rule health analysis
  GET    /health                — API health check
  GET    /months                — Available months list
  DELETE /data                  — Wipe all transactions and imports
  POST   /recategorize          — Re-apply rules to all stored transactions
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from api.models import (
    HealthCheckResponse,
    HealthScoreResponse,
    MonthlySummary,
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
    file: UploadFile = File(..., description="Bank statement .xlsx export"),
    bank: str = Form(default="santander", description="Bank config name (without .yaml)"),
    use_ai: bool = Form(default=False, description="Use Ollama AI categorizer"),
    settings=Depends(get_settings),
    store: SqliteStore = Depends(get_store),
):
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted.")

    banks_dir = Path(__file__).parent.parent.parent / "banks"
    bank_config = banks_dir / f"{bank}.yaml"
    if not bank_config.exists():
        raise HTTPException(status_code=400, detail=f"Unknown bank config: '{bank}'. Available: {[p.stem for p in banks_dir.glob('*.yaml')]}")

    # Save upload to temp file
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
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
    category: str | None = Query(None, description="Filter by category"),
    bank_id: str | None = Query(None, description="Filter by bank"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store: SqliteStore = Depends(get_store),
):
    items = store.get_transactions(
        month=month, category=category, bank_id=bank_id,
        limit=limit, offset=offset,
    )
    # Normalize boolean
    for item in items:
        item["is_reversal"] = bool(item.get("is_reversal"))

    return TransactionList(total=len(items), limit=limit, offset=offset, items=items)


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
