"""
api/review.py — category review queue for opaque marketplace purchases.

Purchases through Vinted, Amazon, Wallapop, PayPal, etc. cannot be
 categorized from the bank statement alone: the real purchase category
(clothing, electronics, books…) differs per item. Marking the merchant
keyword routes those expenses into this review queue.

The review itself reuses PATCH /transactions/{id} (sets category +
category_source='manual'): reviewed items survive recategorizations and
leave the queue. There is intentionally no dedicated write endpoint here.

Endpoints:
  GET    /review-transactions          — queue (+total for the tab badge)
  GET    /review-keywords              — list keywords
  POST   /review-keywords              — add keyword (seeded: Vinted, Amazon, Wallapop, PayPal)
  DELETE /review-keywords/{id}         — remove keyword
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, get_shared_store, get_store
from api.models import (
    ReviewKeyword,
    ReviewKeywordCreateRequest,
    ReviewListResponse,
    ReviewTransactionItem,
)
from db.shared_store import SharedStore
from db.sqlite_store import SqliteStore

router = APIRouter()

DEFAULT_KEYWORDS = ["VINTED", "AMAZON", "WALLAPOP", "PAYPAL"]


@router.get("/review-transactions", response_model=ReviewListResponse)
def get_review_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: SqliteStore = Depends(get_store),
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    keywords = [k["keyword"] for k in shared.get_ambiguous_keywords()]
    data = store.get_review_transactions(keywords, limit=limit, offset=offset)
    items = [
        ReviewTransactionItem(
            id=i["id"],
            date=i["date"],
            description=i["clean_description"] or i["stripped_description"] or i["description"],
            raw_description=i["description"],
            amount=i["amount"],
            balance=i["balance"],
            category=i["category"],
            subcategory=i["subcategory"],
            category_source=i["category_source"],
            proration_months=i["proration_months"],
        )
        for i in data["items"]
    ]
    return ReviewListResponse(total=data["total"], items=items)


@router.get("/review-keywords", response_model=list[ReviewKeyword])
def get_review_keywords(
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    return [ReviewKeyword(**k) for k in shared.get_ambiguous_keywords()]


@router.post("/review-keywords", response_model=ReviewKeyword, status_code=201)
def add_review_keyword(
    body: ReviewKeywordCreateRequest,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    try:
        result = shared.add_ambiguous_keyword(body.keyword)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ReviewKeyword(id=result["id"], keyword=result["keyword"])


@router.delete("/review-keywords/{keyword_id}")
def delete_review_keyword(
    keyword_id: int,
    shared: SharedStore = Depends(get_shared_store),
    _user=Depends(get_current_user),
):
    deleted = shared.delete_ambiguous_keyword(keyword_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Keyword not found.")
    return {"deleted": True, "id": keyword_id}


# Note: default keywords are seeded at app startup (see main.py) so the
# DEFAULT_KEYWORDS constant here is only kept for documentation purposes.
