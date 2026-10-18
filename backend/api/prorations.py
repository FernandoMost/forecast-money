"""
api/prorations.py — expense proration (spread a one-off expense over months).

Prorations never modify the real movements: an allocation stores which months
an expense should be attributed to. Aggregations (summaries, health, trends)
expand the expense into equal monthly fragments (see
db/sqlite_store.expand_allocations); the transactions list keeps showing the
real bank movement with its proration state.

Endpoints:
  GET    /transactions/{id}/proration  — modal context: tx + allocation + similar past expenses
  PUT    /transactions/{id}/proration  — create/replace allocation {months: [YYYY-MM, ...]}
  DELETE /transactions/{id}/proration  — remove allocation (idempotent)
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_store, get_current_user
from api.models import (
    ProrationContextResponse,
    ProrationRequest,
    ProrationResponse,
    SimilarTransactionItem,
    TransactionContext,
)
from db.sqlite_store import SqliteStore

router = APIRouter()

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MIN_MONTHS = 2     # 1 month is not a spread — remove the allocation instead
MAX_MONTHS = 36    # 3 years max (covers a car insurance paid once a year over long data gaps)


def _monthly_amount(amount: float, n_months: int) -> float:
    """Equal-share per month with cent rounding; the last month absorbs the remainder."""
    total = round(abs(amount), 2)
    return round(total / n_months, 2)


def _get_expense_or_404(store: SqliteStore, tx_id: str) -> dict:
    tx = store.get_transaction(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return tx


@router.get("/transactions/{tx_id}/proration", response_model=ProrationContextResponse)
def get_proration(
    tx_id: str,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """Everything the prorate modal needs: the tx, its allocation if any, and similar past expenses."""
    tx = _get_expense_or_404(store, tx_id)
    current_months = store.get_allocations().get(tx_id)
    similar = store.get_similar_transactions(tx_id)
    similar_items = [
        SimilarTransactionItem(
            id=s["id"],
            date=s["date"],
            description=s["clean_description"] or s["description"],
            amount=s["amount"],
            months=s["proration_months"],
        )
        for s in similar
    ]
    return ProrationContextResponse(
        transaction=TransactionContext(
            id=tx["id"],
            date=tx["date"],
            description=tx["clean_description"] or tx["description"],
            amount=tx["amount"],
            month=tx["month"],
            is_reversal=bool(tx["is_reversal"]),
        ),
        months=current_months,
        monthly_amount=_monthly_amount(tx["amount"], len(current_months)) if current_months else None,
        similar=similar_items,
    )


@router.put("/transactions/{tx_id}/proration", response_model=ProrationResponse)
def set_proration(
    tx_id: str,
    body: ProrationRequest,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    tx = _get_expense_or_404(store, tx_id)
    if tx["amount"] >= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Only expenses can be prorated.")
    if tx["is_reversal"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Reversals cannot be prorated.")

    months = sorted(set(body.months))  # dedupe + chronological order
    invalid = [m for m in months if not _MONTH_RE.match(m)]
    if invalid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Months must be YYYY-MM: {invalid[:5]}")
    if len(months) < MIN_MONTHS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"At least {MIN_MONTHS} months are required — "
                                   f"use DELETE to remove the proration.")
    if len(months) > MAX_MONTHS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"At most {MAX_MONTHS} months are allowed.")

    store.set_allocation(tx_id, months)
    return ProrationResponse(
        transaction_id=tx_id,
        months=months,
        monthly_amount=_monthly_amount(tx["amount"], len(months)),
    )


@router.delete("/transactions/{tx_id}/proration", status_code=204)
def delete_proration(
    tx_id: str,
    store: SqliteStore = Depends(get_store),
    _user=Depends(get_current_user),
):
    """Idempotent removal — 204 even if there was no allocation."""
    store.delete_allocation(tx_id)
