"""
db/mongo_store.py

Optional MongoDB persistence layer — only active when MONGO_URI env var is set.
Provides the same interface as SqliteStore so the API layer is unaware of the difference.
Introduced in Phase 5 (cloud mode). Not used in local mode.

To enable: set MONGO_URI=mongodb+srv://... in .env or environment.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient, DESCENDING
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    logger.warning("pymongo/motor not installed — MongoDB mode unavailable.")


class MongoStore:
    """
    Sync MongoDB store using pymongo.
    Drop-in replacement for SqliteStore when MONGO_URI is configured.
    """

    def __init__(self, mongo_uri: str, db_name: str = "finance_analyzer"):
        if not MONGO_AVAILABLE:
            raise RuntimeError("pymongo is not installed. Run: pip install pymongo motor")
        self._client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self._db = self._client[db_name]
        self._txs = self._db["transactions"]
        self._imports = self._db["imports"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self._txs.create_index([("month", DESCENDING)])
        self._txs.create_index([("date", DESCENDING)])
        self._txs.create_index([("category", 1)])
        self._txs.create_index([("id", 1)], unique=True)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def save_import(self, import_id: str, bank_id: str, filename: str, tx_count: int, metadata: dict) -> None:
        self._imports.update_one(
            {"_id": import_id},
            {"$set": {"bank_id": bank_id, "filename": filename, "tx_count": tx_count, "metadata": metadata}},
            upsert=True,
        )

    def list_imports(self) -> list[dict]:
        return list(self._imports.find({}, {"_id": 0}).sort("imported_at", DESCENDING))

    # ------------------------------------------------------------------
    # Transactions — write
    # ------------------------------------------------------------------

    def upsert_transactions(self, transactions: list[dict], import_id: str) -> int:
        inserted = 0
        for tx in transactions:
            doc = {**tx, "import_id": import_id}
            result = self._txs.update_one({"id": tx["id"]}, {"$setOnInsert": doc}, upsert=True)
            if result.upserted_id:
                inserted += 1
        return inserted

    def update_category(self, tx_id: str, category: str, subcategory: str, source: str) -> None:
        self._txs.update_one(
            {"id": tx_id},
            {"$set": {"category": category, "subcategory": subcategory, "category_source": source}},
        )

    # ------------------------------------------------------------------
    # Transactions — read
    # ------------------------------------------------------------------

    def get_transactions(
        self,
        month: str | None = None,
        category: str | None = None,
        bank_id: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict]:
        query: dict[str, Any] = {}
        if month:
            query["month"] = month
        if category:
            query["category"] = category
        if bank_id:
            query["bank_id"] = bank_id

        cursor = (
            self._txs.find(query, {"_id": 0})
            .sort("date", DESCENDING)
            .skip(offset)
            .limit(limit)
        )
        return list(cursor)

    def get_available_months(self) -> list[str]:
        return self._txs.distinct("month")

    def get_monthly_summary(self, month: str) -> dict:
        pipeline = [
            {"$match": {"month": month, "is_reversal": False}},
            {
                "$group": {
                    "_id": None,
                    "tx_count": {"$sum": 1},
                    "total_income": {"$sum": {"$cond": [{"$gt": ["$amount", 0]}, "$amount", 0]}},
                    "total_expenses": {"$sum": {"$cond": [{"$lt": ["$amount", 0]}, "$amount", 0]}},
                    "min_balance": {"$min": "$balance"},
                    "max_balance": {"$max": "$balance"},
                }
            },
        ]
        agg = list(self._txs.aggregate(pipeline))
        if not agg:
            return {"month": month, "tx_count": 0, "total_income": 0, "total_expenses": 0,
                    "net_savings": 0, "savings_rate": 0, "min_balance": 0, "max_balance": 0, "by_category": []}

        a = agg[0]
        income = round(a["total_income"], 2)
        expenses = round(abs(a["total_expenses"]), 2)
        savings = round(income - expenses, 2)

        cat_pipeline = [
            {"$match": {"month": month, "is_reversal": False}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            {"$sort": {"total": 1}},
        ]
        by_cat = [{"category": c["_id"], "total": round(c["total"], 2), "count": c["count"]}
                  for c in self._txs.aggregate(cat_pipeline)]

        return {
            "month": month,
            "tx_count": a["tx_count"],
            "total_income": income,
            "total_expenses": expenses,
            "net_savings": savings,
            "savings_rate": round(savings / income * 100, 1) if income > 0 else 0.0,
            "min_balance": round(a["min_balance"], 2),
            "max_balance": round(a["max_balance"], 2),
            "by_category": by_cat,
        }

    def get_all_transactions_for_rules(self) -> list[dict]:
        return self.get_transactions(limit=100_000)
