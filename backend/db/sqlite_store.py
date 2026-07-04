"""
db/sqlite_store.py

Local SQLite persistence layer.
Stores normalized, categorized transactions and import sessions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class SqliteStore:
    """
    Thin wrapper around a SQLite database for storing transactions.
    Thread-safe via per-call connections (suitable for CLI and FastAPI single-worker use).
    """

    def __init__(self, db_path: str | Path = "data/finance.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS imports (
                    id          TEXT PRIMARY KEY,
                    bank_id     TEXT NOT NULL,
                    filename    TEXT,
                    imported_at TEXT DEFAULT (datetime('now')),
                    tx_count    INTEGER DEFAULT 0,
                    metadata    TEXT   -- JSON blob
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id               TEXT PRIMARY KEY,
                    import_id        TEXT REFERENCES imports(id),
                    bank_id          TEXT NOT NULL,
                    date             TEXT NOT NULL,
                    date_value       TEXT NOT NULL,
                    description      TEXT NOT NULL,
                    amount           REAL NOT NULL,
                    balance          REAL NOT NULL,
                    currency         TEXT NOT NULL DEFAULT 'EUR',
                    is_reversal      INTEGER NOT NULL DEFAULT 0,
                    category         TEXT,
                    subcategory      TEXT,
                    category_source  TEXT,
                    month            TEXT NOT NULL,
                    year             INTEGER NOT NULL,
                    raw_json         TEXT  -- full normalized dict for future schema changes
                );

                CREATE INDEX IF NOT EXISTS idx_tx_month   ON transactions(month);
                CREATE INDEX IF NOT EXISTS idx_tx_date    ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
                CREATE INDEX IF NOT EXISTS idx_tx_bank    ON transactions(bank_id);
            """)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def save_import(self, import_id: str, bank_id: str, filename: str, tx_count: int, metadata: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO imports (id, bank_id, filename, tx_count, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (import_id, bank_id, filename, tx_count, json.dumps(metadata)),
            )

    def list_imports(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, bank_id, filename, imported_at, tx_count FROM imports ORDER BY imported_at DESC"
            ).fetchall()
        return [dict(zip(["id", "bank_id", "filename", "imported_at", "tx_count"], r)) for r in rows]

    # ------------------------------------------------------------------
    # Transactions — write
    # ------------------------------------------------------------------

    def upsert_transactions(self, transactions: list[dict], import_id: str) -> int:
        """Insert or replace transactions. Returns count of new rows inserted."""
        inserted = 0
        with self._connect() as conn:
            for tx in transactions:
                result = conn.execute(
                    """INSERT OR IGNORE INTO transactions
                       (id, import_id, bank_id, date, date_value, description, amount, balance,
                        currency, is_reversal, category, subcategory,
                        category_source, month, year, raw_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tx["id"], import_id, tx["bank_id"],
                        tx["date"], tx["date_value"],
                        tx["description"], tx["amount"], tx["balance"],
                        tx.get("currency", "EUR"),
                        1 if tx.get("is_reversal") else 0,
                        tx.get("category"), tx.get("subcategory"),
                        tx.get("category_source"),
                        tx["month"], tx["year"],
                        json.dumps(tx),
                    ),
                )
                inserted += result.rowcount
        return inserted

    def update_category(self, tx_id: str, category: str, subcategory: str, source: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE transactions SET category=?, subcategory=?, category_source=? WHERE id=?",
                (category, subcategory, source, tx_id),
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
        conditions = []
        params: list[Any] = []

        if month:
            conditions.append("month = ?")
            params.append(month)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if bank_id:
            conditions.append("bank_id = ?")
            params.append(bank_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT id, bank_id, date, date_value, description, amount, balance,
                   currency, is_reversal, category, subcategory,
                   category_source, month, year
            FROM transactions
            {where}
            ORDER BY date DESC
            LIMIT ? OFFSET ?
        """
        params += [limit, offset]

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        cols = ["id", "bank_id", "date", "date_value", "description", "amount",
                "balance", "currency", "is_reversal",
                "category", "subcategory", "category_source", "month", "year"]
        return [dict(zip(cols, r)) for r in rows]

    def get_available_months(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT month FROM transactions ORDER BY month DESC"
            ).fetchall()
        return [r[0] for r in rows]

    def get_monthly_summary(self, month: str) -> dict:
        with self._connect() as conn:
            agg = conn.execute("""
                SELECT
                    COUNT(*)                                              as tx_count,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)     as total_income,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)     as total_expenses,
                    MIN(balance)                                          as min_balance,
                    MAX(balance)                                          as max_balance
                FROM transactions
                WHERE month = ? AND is_reversal = 0
            """, (month,)).fetchone()

            by_category = conn.execute("""
                SELECT category, SUM(amount) as total, COUNT(*) as count
                FROM transactions
                WHERE month = ? AND is_reversal = 0
                GROUP BY category
                ORDER BY total ASC
            """, (month,)).fetchall()

        income = round(agg[1] or 0.0, 2)
        expenses = round(abs(agg[2] or 0.0), 2)
        savings = round(income - expenses, 2)

        return {
            "month": month,
            "tx_count": agg[0] or 0,
            "total_income": income,
            "total_expenses": expenses,
            "net_savings": savings,
            "savings_rate": round(savings / income * 100, 1) if income > 0 else 0.0,
            "min_balance": round(agg[3] or 0.0, 2),
            "max_balance": round(agg[4] or 0.0, 2),
            "by_category": [
                {"category": r[0], "total": round(r[1], 2), "count": r[2]}
                for r in by_category
            ],
        }

    def get_all_transactions_for_rules(self) -> list[dict]:
        """Returns all non-reversal transactions for the health engine."""
        return self.get_transactions(limit=100_000)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
