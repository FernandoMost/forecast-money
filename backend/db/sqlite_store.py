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

                CREATE TABLE IF NOT EXISTS expense_allocations (
                    transaction_id TEXT PRIMARY KEY REFERENCES transactions(id),
                    months         TEXT NOT NULL,   -- JSON array of "YYYY-MM"
                    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
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
            conn.execute("DELETE FROM expense_allocations WHERE transaction_id IN (SELECT id FROM transactions WHERE import_id = ?)")
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
        order_clause = f"ORDER BY t.{sort_by} {order}, t.rowid {order}"
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
                SELECT t.id, t.bank_id, t.date, t.date_value, t.description, t.stripped_description,
                       t.clean_description, t.clean_description_source, t.amount, t.balance,
                       t.currency, t.is_reversal, t.category, t.subcategory,
                       t.category_source, t.month, t.year, ea.months AS proration_months
                FROM transactions t
                LEFT JOIN expense_allocations ea ON ea.transaction_id = t.id
                {where}
                {order_clause}
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

        cols = ["id", "bank_id", "date", "date_value", "description", "stripped_description",
                "clean_description", "clean_description_source",
                "amount", "balance", "currency", "is_reversal",
                "category", "subcategory", "category_source", "month", "year",
                "proration_months"]
        items: list[dict] = []
        for r in rows:
            item = dict(zip(cols, r))
            if item.get("proration_months"):
                try:
                    item["proration_months"] = json.loads(item["proration_months"])
                except (json.JSONDecodeError, TypeError):
                    item["proration_months"] = None
            items.append(item)
        return {"total": total_count, "amount_total": amount_total, "items": items}

    def get_available_months(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT month FROM transactions ORDER BY month DESC"
            ).fetchall()
        return [r[0] for r in rows]

    def get_monthly_summary(self, month: str) -> dict:
        # Real-side figures: movement count and balance range (balances are bank
        # reality and are never prorated).
        with self._connect() as conn:
            real = conn.execute("""
                SELECT COUNT(*), MIN(balance), MAX(balance)
                FROM transactions
                WHERE month = ? AND is_reversal = 0
            """, (month,)).fetchone()

        # Income/expenses/by_category use prorated amounts (see expense_allocations).
        total_income, total_expenses, by_category = self._allocated_month_totals(month)
        expenses = round(abs(total_expenses), 2)
        savings = round(total_income - expenses, 2)

        return {
            "month": month,
            "tx_count": real[0] or 0,
            "total_income": total_income,
            "total_expenses": expenses,
            "net_savings": savings,
            "savings_rate": round(savings / total_income * 100, 1) if total_income > 0 else 0.0,
            "min_balance": round(real[1], 2) if real[1] is not None else None,
            "max_balance": round(real[2], 2) if real[2] is not None else None,
            "by_category": by_category,
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
            # Real-side figures only: counts, balances and dates are bank reality
            # and are never prorated.
            real = conn.execute("""
                SELECT
                    COUNT(*), MIN(balance), MAX(balance),
                    MIN(date), MAX(date)
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

        # Income/expenses/leisure/by_category use prorated amounts.
        total_income, total_expenses, by_category = self._allocated_month_totals(month)
        if leisure_category_ids:
            leisure_txs = self.get_all_transactions_for_rules()
            leisure_month = [
                t for t in self.expand_allocations(leisure_txs)
                if t.get("month") == month and not t.get("is_reversal")
                and t["amount"] < 0 and t.get("category") in set(leisure_category_ids)
            ]
            leisure_spent = round(sum(abs(t["amount"]) for t in leisure_month), 2)
        else:
            leisure_spent = 0.0

        first_date = real[3]
        last_date = real[4]

        # days_of_data: span of dates in this month's data
        days_of_data = 0
        if first_date and last_date:
            from datetime import date as _date
            d0 = _date.fromisoformat(first_date)
            d1 = _date.fromisoformat(last_date)
            days_of_data = (d1 - d0).days + 1

        return {
            "month": month,
            "tx_count": real[0] or 0,
            "total_income": total_income,
            "total_expenses": round(abs(total_expenses), 2),
            "net_savings": round(total_income - abs(total_expenses), 2),
            "drew_from_savings": (total_income - abs(total_expenses)) < 0,
            "savings_rate": round((total_income - abs(total_expenses)) / total_income * 100, 1) if total_income > 0 else 0.0,
            "min_balance": round(real[1], 2) if real[1] is not None else None,
            "max_balance": round(real[2], 2) if real[2] is not None else None,
            "last_balance": round(last_row[0], 2) if last_row else None,
            "last_balance_date": last_row[1] if last_row else None,
            "leisure_spent": leisure_spent,
            "days_of_data": days_of_data,
            "first_date": first_date,
            "last_date": last_date,
            "by_category": by_category,
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
            conn.execute("DELETE FROM expense_allocations")
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

    # ------------------------------------------------------------------
    # Expense proration — spread a one-off expense over several months
    # ------------------------------------------------------------------
    # Real transactions are never modified: allocations store which months
    # each expense should be attributed to. Aggregations (summaries, health,
    # trends) expand the expense into equal monthly fragments; the raw
    # movements list (balances, counts, dates) keeps showing bank reality.

    def get_transaction(self, tx_id: str) -> dict | None:
        """Returns a single transaction (id, amount, dates, description) or None."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, bank_id, date, description, stripped_description,
                          clean_description, clean_description_source, amount, balance,
                          currency, is_reversal, category, subcategory, month, year
                   FROM transactions WHERE id = ?""",
                (tx_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_allocations(self) -> dict[str, list[str]]:
        """Returns {transaction_id: [month, ...]} for every expense proration."""
        with self._connect() as conn:
            rows = conn.execute("SELECT transaction_id, months FROM expense_allocations").fetchall()
        return {r["transaction_id"]: json.loads(r["months"]) for r in rows}

    def set_allocation(self, transaction_id: str, months: list[str]) -> None:
        """Create or replace the proration for a transaction (upsert)."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO expense_allocations (transaction_id, months)
                   VALUES (?, ?)
                   ON CONFLICT(transaction_id) DO UPDATE SET
                       months     = excluded.months,
                       updated_at = datetime('now')""",
                (transaction_id, json.dumps(months)),
            )

    def delete_allocation(self, transaction_id: str) -> bool:
        """Remove a proration. Returns True if one was deleted."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM expense_allocations WHERE transaction_id = ?", (transaction_id,)
            )
        return result.rowcount > 0

    def get_similar_transactions(self, tx_id: str, limit: int = 10) -> list[dict]:
        """
        Past expenses with the same label (COALESCE(clean_description, description))
        as the given transaction, excluding itself, newest first, each with its
        proration state if any.
        """
        with self._connect() as conn:
            base = conn.execute(
                "SELECT id, COALESCE(clean_description, description) AS label FROM transactions WHERE id = ?",
                (tx_id,),
            ).fetchone()
            if base is None:
                return []
            rows = conn.execute(
                """SELECT t.id, t.date, t.description, t.clean_description, t.amount,
                          ea.months AS proration_months
                   FROM transactions t
                   LEFT JOIN expense_allocations ea ON ea.transaction_id = t.id
                   WHERE t.id != ?
                     AND t.is_reversal = 0
                     AND t.amount < 0
                     AND COALESCE(t.clean_description, t.description) = ?
                   ORDER BY t.date DESC, t.rowid DESC
                   LIMIT ?""",
                (tx_id, base["label"], limit),
            ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            item["proration_months"] = json.loads(item["proration_months"]) if item["proration_months"] else None
            items.append(item)
        return items

    def expand_allocations(self, transactions: list[dict]) -> list[dict]:
        """
        Replace prorated expenses with one fragment per assigned month for
        aggregation purposes. Returns a new list; the input is not modified.

        Split keeps the total exact to the cent: every fragment gets base =
        round(total / n) and the last fragment absorbs the rounding remainder.
        """
        allocations = self.get_allocations()
        if not allocations:
            return transactions
        expanded: list[dict] = []
        for tx in transactions:
            months = allocations.get(tx["id"])
            if not months or tx["amount"] >= 0 or tx.get("is_reversal"):
                expanded.append(tx)
                continue
            n = len(months)
            if n <= 1:
                expanded.append(tx)
                continue
            total = round(abs(float(tx["amount"])), 2)
            base = round(total / n, 2)
            for i, m in enumerate(months):
                frag = dict(tx)
                frag["amount"] = round(-(total - base * (n - 1)), 2) if i == n - 1 else -base
                frag["date"] = f"{m}-01"
                frag["month"] = m
                frag["year"] = int(m[:4])
                frag["prorated"] = True
                expanded.append(frag)
        return expanded

    def _allocated_month_totals(self, month: str) -> tuple[float, float, list[dict]]:
        """
        Income/expenses/by_category for one month, expenses-reality adjusted by
        prorations. by_category 'count' counts fragments (a prorated expense
        contributes to each assigned month).
        """
        all_txs = self.get_all_transactions_for_rules()
        expanded = self.expand_allocations(all_txs)
        month_txs = [
            t for t in expanded
            if t.get("month") == month and not t.get("is_reversal")
        ]
        total_income = round(sum(t["amount"] for t in month_txs if t["amount"] > 0), 2)
        total_expenses = round(-sum(t["amount"] for t in month_txs if t["amount"] < 0), 2)

        by_cat: dict[str, dict] = {}
        for t in month_txs:
            slot = by_cat.setdefault(t.get("category"), {"total": 0.0, "count": 0})
            slot["total"] += t["amount"]
            slot["count"] += 1
        rows = [
            {"category": cat, "total": round(v["total"], 2), "count": v["count"]}
            for cat, v in by_cat.items()
        ]
        rows.sort(key=lambda r: r["total"])
        return total_income, total_expenses, rows
