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
                    id                       TEXT PRIMARY KEY,
                    import_id                TEXT REFERENCES imports(id),
                    bank_id                  TEXT NOT NULL,
                    date                     TEXT NOT NULL,
                    date_value               TEXT NOT NULL,
                    description              TEXT NOT NULL,
                    clean_description        TEXT,
                    clean_description_source TEXT,
                    amount                   REAL NOT NULL,
                    balance                  REAL NOT NULL,
                    currency                 TEXT NOT NULL DEFAULT 'EUR',
                    is_reversal              INTEGER NOT NULL DEFAULT 0,
                    category                 TEXT,
                    subcategory              TEXT,
                    category_source          TEXT,
                    month                    TEXT NOT NULL,
                    year                     INTEGER NOT NULL,
                    raw_json                 TEXT  -- full normalized dict for future schema changes
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
                       (id, import_id, bank_id, date, date_value, description,
                        clean_description, clean_description_source,
                        amount, balance, currency, is_reversal, category, subcategory,
                        category_source, month, year, raw_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tx["id"], import_id, tx["bank_id"],
                        tx["date"], tx["date_value"],
                        tx["description"],
                        tx.get("clean_description"), tx.get("clean_description_source"),
                        tx["amount"], tx["balance"],
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

    def bulk_update_categories(self, updates: list[dict]) -> int:
        """
        Apply category + clean_description updates to multiple transactions at once.
        Each dict must have: id, category, subcategory, category_source,
                             clean_description, clean_description_source.
        Returns the number of rows updated.
        """
        updated = 0
        with self._connect() as conn:
            for u in updates:
                result = conn.execute(
                    """UPDATE transactions
                       SET category=?, subcategory=?, category_source=?,
                           clean_description=?, clean_description_source=?
                       WHERE id=?""",
                    (
                        u["category"], u["subcategory"], u["category_source"],
                        u.get("clean_description"), u.get("clean_description_source"),
                        u["id"],
                    ),
                )
                updated += result.rowcount
        return updated

    def update_transaction_manual(
        self,
        tx_id: str,
        clean_description: str | None,
        category: str | None,
        subcategory: str | None,
    ) -> bool:
        """
        Manually override clean_description and/or category for a single transaction.
        Sets the corresponding _source fields to 'manual'.
        Returns True if a row was updated.
        """
        with self._connect() as conn:
            result = conn.execute(
                """UPDATE transactions
                   SET clean_description        = ?,
                       clean_description_source = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE clean_description_source END,
                       category                 = COALESCE(?, category),
                       subcategory              = COALESCE(?, subcategory),
                       category_source          = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE category_source END
                   WHERE id = ?""",
                (
                    clean_description,
                    clean_description,   # for the CASE
                    category,
                    subcategory,
                    category,            # for the CASE
                    tx_id,
                ),
            )
        return result.rowcount > 0

    def get_transaction_by_id(self, tx_id: str) -> dict | None:
        """Returns a single transaction by id, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, bank_id, date, date_value, description, clean_description,
                          clean_description_source, amount, balance, currency, is_reversal,
                          category, subcategory, category_source, month, year
                   FROM transactions WHERE id = ?""",
                (tx_id,),
            ).fetchone()
        if not row:
            return None
        cols = ["id", "bank_id", "date", "date_value", "description",
                "clean_description", "clean_description_source",
                "amount", "balance", "currency", "is_reversal",
                "category", "subcategory", "category_source", "month", "year"]
        return dict(zip(cols, row))
        """Returns id + description for every transaction — used by recategorize."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, description FROM transactions ORDER BY date DESC"
            ).fetchall()
        return [{"id": r[0], "description": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Transactions — read
    # ------------------------------------------------------------------

    def get_transactions(
        self,
        month: str | None = None,
        year: int | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        bank_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """
        Returns paginated transactions plus total count and amount_total for the full
        (unpaginated) query — so the frontend can show accurate pagination and totals.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if month:
            conditions.append("month = ?")
            params.append(month)
        elif year:
            conditions.append("year = ?")
            params.append(year)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if subcategory:
            conditions.append("subcategory = ?")
            params.append(subcategory)
        if bank_id:
            conditions.append("bank_id = ?")
            params.append(bank_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._connect() as conn:
            # Aggregate for total count + total amount (full query, no pagination)
            agg_row = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions {where}",
                params,
            ).fetchone()
            total_count = agg_row[0]
            amount_total = round(agg_row[1], 2)

            # Paginated rows
            rows = conn.execute(
                f"""
                SELECT id, bank_id, date, date_value, description, clean_description,
                       clean_description_source, amount, balance,
                       currency, is_reversal, category, subcategory,
                       category_source, month, year
                FROM transactions
                {where}
                ORDER BY date DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

        cols = ["id", "bank_id", "date", "date_value", "description",
                "clean_description", "clean_description_source",
                "amount", "balance", "currency", "is_reversal",
                "category", "subcategory", "category_source", "month", "year"]
        items = [dict(zip(cols, r)) for r in rows]
        return {"total": total_count, "amount_total": amount_total, "items": items}

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
        """Returns all transactions for the health engine (no pagination)."""
        result = self.get_transactions(limit=100_000)
        return result["items"]

    def get_latest_transaction_date(self) -> str | None:
        """Returns the date string (YYYY-MM-DD) of the most recent transaction, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM transactions WHERE is_reversal = 0"
            ).fetchone()
        return row[0] if row and row[0] else None

    def get_dashboard_month_summary(self, month: str) -> dict:
        """
        Extended monthly summary for the dashboard.
        Adds: days_of_data (days between first and last tx in the month),
        last_balance (balance of the most recent transaction in the month),
        last_balance_date, and leisure_spent (restaurants + entertainment).
        """
        with self._connect() as conn:
            agg = conn.execute("""
                SELECT
                    COUNT(*)                                              as tx_count,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)     as total_income,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)     as total_expenses,
                    MIN(balance)                                          as min_balance,
                    MAX(balance)                                          as max_balance,
                    MIN(date)                                             as first_date,
                    MAX(date)                                             as last_date
                FROM transactions
                WHERE month = ? AND is_reversal = 0
            """, (month,)).fetchone()

            # Balance of the very last transaction in this month
            last_row = conn.execute("""
                SELECT balance, date FROM transactions
                WHERE month = ? AND is_reversal = 0
                ORDER BY date DESC, rowid DESC
                LIMIT 1
            """, (month,)).fetchone()

            # Leisure = restaurants + entertainment
            leisure_row = conn.execute("""
                SELECT COALESCE(SUM(ABS(amount)), 0)
                FROM transactions
                WHERE month = ? AND is_reversal = 0
                  AND amount < 0
                  AND category IN ('restaurants', 'entertainment')
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
        first_date = agg[5]
        last_date = agg[6]

        # days_of_data: span of dates in this month's data
        days_of_data = 0
        if first_date and last_date:
            from datetime import date as _date
            d0 = _date.fromisoformat(first_date)
            d1 = _date.fromisoformat(last_date)
            days_of_data = (d1 - d0).days + 1

        return {
            "month": month,
            "tx_count": agg[0] or 0,
            "total_income": income,
            "total_expenses": expenses,
            "net_savings": savings,
            "drew_from_savings": savings < 0,
            "savings_rate": round(savings / income * 100, 1) if income > 0 else 0.0,
            "min_balance": round(agg[3] or 0.0, 2),
            "max_balance": round(agg[4] or 0.0, 2),
            "last_balance": round(last_row[0], 2) if last_row else None,
            "last_balance_date": last_row[1] if last_row else None,
            "leisure_spent": round(leisure_row[0] or 0.0, 2),
            "days_of_data": days_of_data,
            "first_date": first_date,
            "last_date": last_date,
            "by_category": [
                {"category": r[0], "total": round(r[1], 2), "count": r[2]}
                for r in by_category
            ],
        }

    def clear_all(self) -> dict:
        """Deletes all transactions and imports. Returns counts of deleted rows."""
        with self._connect() as conn:
            tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            import_count = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM imports")
        return {"deleted_transactions": tx_count, "deleted_imports": import_count}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
