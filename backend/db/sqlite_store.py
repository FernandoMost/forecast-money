"""
db/sqlite_store.py

Local SQLite persistence layer.
Stores normalized, categorized transactions and import sessions.

Note: categories are now in data/shared.db (SharedStore), not here.
"""

from __future__ import annotations

import json
import sqlite3
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

                CREATE TABLE IF NOT EXISTS health_score_history (
                    id          TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    import_id   TEXT REFERENCES imports(id),
                    overall_score REAL NOT NULL,
                    grade       TEXT NOT NULL,
                    rule_scores TEXT NOT NULL  -- JSON: {rule_id: score}
                );

                CREATE TABLE IF NOT EXISTS description_strip_config (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    type       TEXT NOT NULL CHECK(type IN ('prefix', 'suffix')),
                    value      TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(type, value)
                );

                CREATE TABLE IF NOT EXISTS suggestion_dismissed (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    description  TEXT NOT NULL UNIQUE,
                    dismissed_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_tx_month    ON transactions(month);
                CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
                CREATE INDEX IF NOT EXISTS idx_tx_bank     ON transactions(bank_id);
                CREATE INDEX IF NOT EXISTS idx_hsh_date    ON health_score_history(recorded_at);
            """)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply incremental schema changes to existing databases."""
        with self._connect() as conn:
            # Add stripped_description column if it doesn't exist yet
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(transactions)").fetchall()
            }
            if "stripped_description" not in existing:
                conn.execute(
                    "ALTER TABLE transactions ADD COLUMN stripped_description TEXT"
                )

    # ------------------------------------------------------------------
    # Health score history
    # ------------------------------------------------------------------

    def save_health_score(
        self,
        import_id: str | None,
        overall_score: float,
        grade: str,
        rule_scores: dict[str, float],
    ) -> None:
        """Persist a health score snapshot after an import."""
        import uuid as _uuid
        record_id = _uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO health_score_history
                   (id, import_id, overall_score, grade, rule_scores)
                   VALUES (?, ?, ?, ?, ?)""",
                (record_id, import_id, overall_score, grade, json.dumps(rule_scores)),
            )

    def get_health_score_history(self, limit: int = 50) -> list[dict]:
        """Returns health score history, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, recorded_at, import_id, overall_score, grade, rule_scores
                   FROM health_score_history
                   ORDER BY recorded_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "recorded_at": r[1],
                "import_id": r[2],
                "overall_score": r[3],
                "grade": r[4],
                "rule_scores": json.loads(r[5]) if r[5] else {},
            })
        return result

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
                "SELECT id, bank_id, filename, imported_at, tx_count, metadata FROM imports ORDER BY imported_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            item = dict(zip(["id", "bank_id", "filename", "imported_at", "tx_count", "metadata"], r))
            try:
                item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                item["metadata"] = {}
            result.append(item)
        return result

    def delete_import(self, import_id: str) -> dict:
        """Deletes a single import and all its associated transactions and health score history."""
        with self._connect() as conn:
            tx_count = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE import_id = ?", (import_id,)
            ).fetchone()[0]
            conn.execute("DELETE FROM health_score_history WHERE import_id = ?", (import_id,))
            conn.execute("DELETE FROM transactions WHERE import_id = ?", (import_id,))
            conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))
        return {"deleted_transactions": tx_count}

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
                        stripped_description,
                        clean_description, clean_description_source,
                        amount, balance, currency, is_reversal, category, subcategory,
                        category_source, month, year, raw_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tx["id"], import_id, tx["bank_id"],
                        tx["date"], tx["date_value"],
                        tx["description"],
                        tx.get("stripped_description"),
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

    def update_transaction_category(self, tx_id: str, category: str, subcategory: str, source: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE transactions SET category=?, subcategory=?, category_source=? WHERE id=?",
                (category, subcategory, source, tx_id),
            )

    def bulk_update_categories(self, updates: list[dict]) -> int:
        """
        Apply category + clean_description + stripped_description updates to multiple transactions at once.
        Each dict must have: id, category, subcategory, category_source,
                             clean_description, clean_description_source, stripped_description.
        Manual edits (source='manual') are never overwritten.
        Returns the number of rows updated.
        """
        updated = 0
        with self._connect() as conn:
            for u in updates:
                result = conn.execute(
                    """UPDATE transactions
                       SET category             = CASE WHEN category_source = 'manual' THEN category ELSE ? END,
                           subcategory          = CASE WHEN category_source = 'manual' THEN subcategory ELSE ? END,
                           category_source      = CASE WHEN category_source = 'manual' THEN 'manual' ELSE ? END,
                           clean_description        = CASE WHEN clean_description_source IN ('manual', 'clean') THEN clean_description ELSE ? END,
                           clean_description_source = CASE WHEN clean_description_source IN ('manual', 'clean') THEN clean_description_source ELSE ? END,
                           stripped_description     = CASE WHEN clean_description_source IN ('manual', 'clean') THEN stripped_description ELSE ? END
                       WHERE id=?""",
                    (
                        u["category"], u["subcategory"], u["category_source"],
                        u.get("clean_description"), u.get("clean_description_source"),
                        u.get("stripped_description"),
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
        month: str | None = None,
    ) -> bool:
        """
        Manually override clean_description, category and/or month for a single transaction.
        When month is provided (YYYY-MM), date is set to the 1st of that month and year is
        derived accordingly. Sets the corresponding _source fields to 'manual'.
        Returns True if a row was updated.
        """
        with self._connect() as conn:
            if month is not None:
                year = int(month[:4])
                new_date = f"{month}-01"
                result = conn.execute(
                    """UPDATE transactions
                       SET clean_description        = COALESCE(?, clean_description),
                           clean_description_source = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE clean_description_source END,
                           category                 = COALESCE(?, category),
                           subcategory              = COALESCE(?, subcategory),
                           category_source          = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE category_source END,
                           month                    = ?,
                           year                     = ?,
                           date                     = ?
                       WHERE id = ?""",
                    (
                        clean_description,
                        clean_description,
                        category,
                        subcategory,
                        category,
                        month,
                        year,
                        new_date,
                        tx_id,
                    ),
                )
            else:
                result = conn.execute(
                    """UPDATE transactions
                       SET clean_description        = COALESCE(?, clean_description),
                           clean_description_source = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE clean_description_source END,
                           category                 = COALESCE(?, category),
                           subcategory              = COALESCE(?, subcategory),
                           category_source          = CASE WHEN ? IS NOT NULL THEN 'manual' ELSE category_source END
                       WHERE id = ?""",
                    (
                        clean_description,
                        clean_description,
                        category,
                        subcategory,
                        category,
                        tx_id,
                    ),
                )
        return result.rowcount > 0

    def get_transaction_by_id(self, tx_id: str) -> dict | None:
        """Returns a single transaction by id, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, bank_id, date, date_value, description, stripped_description,
                          clean_description, clean_description_source,
                          amount, balance, currency, is_reversal,
                          category, subcategory, category_source, month, year
                   FROM transactions WHERE id = ?""",
                (tx_id,),
            ).fetchone()
        if not row:
            return None
        cols = ["id", "bank_id", "date", "date_value", "description", "stripped_description",
                "clean_description", "clean_description_source",
                "amount", "balance", "currency", "is_reversal",
                "category", "subcategory", "category_source", "month", "year"]
        return dict(zip(cols, row))

    def get_all_descriptions(self) -> list[dict]:
        """Returns id + bank_id + description + stripped_description for every transaction
        that still needs categorization (excludes manual and clean edits)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, bank_id, description, stripped_description
                   FROM transactions
                   WHERE clean_description_source NOT IN ('manual', 'clean')
                      OR clean_description_source IS NULL
                   ORDER BY date DESC"""
            ).fetchall()
        return [{"id": r[0], "bank_id": r[1], "description": r[2], "stripped_description": r[3]} for r in rows]

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
        clean_description: str | None = None,
        uncleaned: bool = False,
        sort_by: str = "date",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """
        Returns paginated transactions plus total count and amount_total for the full
        (unpaginated) query — so the frontend can show accurate pagination and totals.

        sort_by must be one of the allowed column names (whitelist to prevent injection).
        sort_dir must be 'asc' or 'desc'.
        """
        _SORTABLE = {"date", "amount", "balance", "description", "category", "month"}
        if sort_by not in _SORTABLE:
            sort_by = "date"
        order = "DESC" if sort_dir.lower() == "desc" else "ASC"
        # Always add rowid as tiebreaker for stable pagination
        order_clause = f"ORDER BY {sort_by} {order}, rowid {order}"
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
        if clean_description is not None:
            conditions.append("clean_description = ?")
            params.append(clean_description)
        if uncleaned:
            conditions.append(
                "(clean_description IS NULL"
                " AND (clean_description_source IS NULL"
                "      OR clean_description_source NOT IN ('manual', 'clean')))"
            )

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
                SELECT id, bank_id, date, date_value, description, stripped_description,
                       clean_description, clean_description_source, amount, balance,
                       currency, is_reversal, category, subcategory,
                       category_source, month, year
                FROM transactions
                {where}
                {order_clause}
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

        cols = ["id", "bank_id", "date", "date_value", "description", "stripped_description",
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

    def get_latest_balance(self) -> dict:
        """Returns the balance and date of the most recent non-reversal transaction across all data."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT balance, date FROM transactions WHERE is_reversal = 0 ORDER BY date DESC, rowid DESC LIMIT 1"
            ).fetchone()
        if row:
            return {"balance": round(row[0], 2), "date": row[1]}
        return {"balance": None, "date": None}

    def get_dashboard_month_summary(self, month: str, leisure_category_ids: list[str] | None = None) -> dict:
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

            # Leisure = categories passed in (from shared.db role='leisure')
            if leisure_category_ids:
                placeholders = ",".join("?" * len(leisure_category_ids))
                leisure_row = conn.execute(
                    f"""SELECT COALESCE(SUM(ABS(t.amount)), 0)
                        FROM transactions t
                        WHERE t.month = ? AND t.is_reversal = 0
                          AND t.amount < 0
                          AND t.category IN ({placeholders})""",
                    [month] + list(leisure_category_ids),
                ).fetchone()
            else:
                leisure_row = conn.execute(
                    "SELECT 0.0"
                ).fetchone()

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

    def get_uncategorized_by_clean_description(self) -> list[dict]:
        """
        Returns groups of transactions that have a clean_description but are uncategorized
        (category IS NULL or category = 'uncategorized'), grouped by clean_description.
        Each entry: clean_description, count, latest_date.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT clean_description, COUNT(*) as c, MAX(date) as latest
                   FROM transactions
                   WHERE clean_description IS NOT NULL
                     AND (category IS NULL OR category = 'uncategorized')
                   GROUP BY clean_description
                   ORDER BY c DESC, latest DESC"""
            ).fetchall()
        return [
            {"clean_description": r[0], "count": r[1], "latest_date": r[2]}
            for r in rows
        ]

    def bulk_set_category_for_clean_description(
        self, clean_description: str, category: str, subcategory: str | None
    ) -> int:
        """
        Set category + subcategory + category_source='rule' for all transactions
        matching clean_description that are uncategorized (not manually set).
        Returns the number of rows updated.
        """
        with self._connect() as conn:
            result = conn.execute(
                """UPDATE transactions
                   SET category        = ?,
                       subcategory     = ?,
                       category_source = 'rule'
                   WHERE clean_description = ?
                     AND category_source != 'manual'
                     AND (category IS NULL OR category = 'uncategorized')""",
                (category, subcategory, clean_description),
            )
        return result.rowcount

    def clear_all(self) -> dict:
        """Deletes all transactions and imports. Returns counts of deleted rows."""
        with self._connect() as conn:
            tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            import_count = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM imports")
        return {"deleted_transactions": tx_count, "deleted_imports": import_count}

    # ------------------------------------------------------------------
    # Description strip config (per-user prefixes/suffixes)
    # ------------------------------------------------------------------

    def get_strip_config(self) -> list[dict]:
        """Returns all strip config entries ordered by type then created_at."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, type, value, created_at FROM description_strip_config ORDER BY type, created_at"
            ).fetchall()
        return [{"id": r[0], "type": r[1], "value": r[2], "created_at": r[3]} for r in rows]

    def add_strip_entry(self, entry_type: str, value: str) -> dict:
        """Insert a prefix or suffix. Raises ValueError on duplicate."""
        if entry_type not in ("prefix", "suffix"):
            raise ValueError(f"Invalid type '{entry_type}'. Must be 'prefix' or 'suffix'.")
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO description_strip_config (type, value) VALUES (?, ?)",
                    (entry_type, value),
                )
                row_id = cursor.lastrowid
            except Exception:
                raise ValueError(f"Entry ({entry_type}, '{value}') already exists.")
            row = conn.execute(
                "SELECT id, type, value, created_at FROM description_strip_config WHERE id = ?",
                (row_id,),
            ).fetchone()
        return {"id": row[0], "type": row[1], "value": row[2], "created_at": row[3]}

    def delete_strip_entry(self, entry_id: int) -> bool:
        """Delete a strip config entry by id. Returns True if deleted."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM description_strip_config WHERE id = ?", (entry_id,)
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Suggestion dismissed
    # ------------------------------------------------------------------

    def get_dismissed_descriptions(self) -> set[str]:
        """Returns the set of descriptions the user has permanently dismissed."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT description FROM suggestion_dismissed"
            ).fetchall()
        return {r[0] for r in rows}

    def add_dismissed_description(self, description: str) -> None:
        """Permanently dismiss a description from suggestions (INSERT OR IGNORE)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO suggestion_dismissed (description) VALUES (?)",
                (description,),
            )

    def remove_dismissed_description(self, description: str) -> bool:
        """Un-dismiss a description. Returns True if a row was removed."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM suggestion_dismissed WHERE description = ?", (description,)
            )
        return result.rowcount > 0

    def mark_description_clean(self, description: str, label: str) -> int:
        """
        Set clean_description = label, clean_description_source = 'clean' for every
        transaction whose COALESCE(stripped_description, description) matches.
        Skips rows already marked 'manual'.
        Returns number of rows updated.
        """
        with self._connect() as conn:
            result = conn.execute(
                """UPDATE transactions
                   SET clean_description        = ?,
                       clean_description_source = 'clean'
                   WHERE COALESCE(stripped_description, description) = ?
                     AND (clean_description_source IS NULL
                          OR clean_description_source NOT IN ('manual'))""",
                (label, description),
            )
        return result.rowcount

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
