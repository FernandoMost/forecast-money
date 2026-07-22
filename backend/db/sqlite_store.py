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

# Default category taxonomy seeded from config/category_rules.yaml.
# role values: needs | wants | leisure | fixed | savings | income | other
_DEFAULT_CATEGORIES: list[dict] = [
    # Top-level categories
    {"id": "income",        "name": "Income",        "parent_id": None, "color": "#84cc16", "role": "income",  "position": 0},
    {"id": "housing",       "name": "Housing",       "parent_id": None, "color": "#6366f1", "role": "fixed",   "position": 1},
    {"id": "subscriptions", "name": "Subscriptions", "parent_id": None, "color": "#a855f7", "role": "subscriptions", "position": 2},
    {"id": "groceries",     "name": "Groceries",     "parent_id": None, "color": "#22c55e", "role": "needs",   "position": 3},
    {"id": "restaurants",   "name": "Restaurants",   "parent_id": None, "color": "#f97316", "role": "leisure", "position": 4},
    {"id": "transport",     "name": "Transport",     "parent_id": None, "color": "#0ea5e9", "role": "needs",   "position": 5},
    {"id": "health",        "name": "Health",        "parent_id": None, "color": "#14b8a6", "role": "needs",   "position": 6},
    {"id": "shopping",      "name": "Shopping",      "parent_id": None, "color": "#ec4899", "role": "wants",   "position": 7},
    {"id": "entertainment", "name": "Entertainment", "parent_id": None, "color": "#eab308", "role": "leisure", "position": 8},
    {"id": "transfers",     "name": "Transfers",     "parent_id": None, "color": "#94a3b8", "role": "other",   "position": 9},
    {"id": "cash",          "name": "Cash",          "parent_id": None, "color": "#78716c", "role": "other",   "position": 10},
    {"id": "admin",         "name": "Admin",         "parent_id": None, "color": "#64748b", "role": "needs",   "position": 11},
    {"id": "uncategorized", "name": "Uncategorized", "parent_id": None, "color": "#d1d5db", "role": "other",   "position": 12},
    # Subcategories — income
    {"id": "payroll",               "name": "Payroll",          "parent_id": "income",        "color": None, "role": None, "position": 0},
    {"id": "transfer_in",           "name": "Transfer in",      "parent_id": "income",        "color": None, "role": None, "position": 1},
    {"id": "bizum_in",              "name": "Bizum in",         "parent_id": "income",        "color": None, "role": None, "position": 2},
    {"id": "refund",                "name": "Refund",           "parent_id": "income",        "color": None, "role": None, "position": 3},
    {"id": "paypal_in",             "name": "PayPal in",        "parent_id": "income",        "color": None, "role": None, "position": 4},
    # Subcategories — housing
    {"id": "rent",                  "name": "Rent",             "parent_id": "housing",       "color": None, "role": None, "position": 0},
    {"id": "utilities_electricity", "name": "Electricity",      "parent_id": "housing",       "color": None, "role": None, "position": 1},
    {"id": "utilities_water",       "name": "Water",            "parent_id": "housing",       "color": None, "role": None, "position": 2},
    {"id": "utilities_heating",     "name": "Heating",          "parent_id": "housing",       "color": None, "role": None, "position": 3},
    {"id": "internet_phone",        "name": "Internet / Phone", "parent_id": "housing",       "color": None, "role": None, "position": 4},
    # Subcategories — subscriptions
    {"id": "streaming",             "name": "Streaming",        "parent_id": "subscriptions", "color": None, "role": None, "position": 0},
    {"id": "gym",                   "name": "Gym",              "parent_id": "subscriptions", "color": None, "role": None, "position": 1},
    {"id": "sports_club",           "name": "Sports club",      "parent_id": "subscriptions", "color": None, "role": None, "position": 2},
    {"id": "paypal_sub",            "name": "PayPal sub",       "parent_id": "subscriptions", "color": None, "role": None, "position": 3},
    {"id": "pagatelia",             "name": "Pagatelia",        "parent_id": "subscriptions", "color": None, "role": None, "position": 4},
    {"id": "other_sub",             "name": "Other sub",        "parent_id": "subscriptions", "color": None, "role": None, "position": 5},
    # Subcategories — groceries
    {"id": "supermarket",           "name": "Supermarket",      "parent_id": "groceries",     "color": None, "role": None, "position": 0},
    {"id": "other_food_shop",       "name": "Other food shop",  "parent_id": "groceries",     "color": None, "role": None, "position": 1},
    # Subcategories — restaurants
    {"id": "fast_food",             "name": "Fast food",        "parent_id": "restaurants",   "color": None, "role": None, "position": 0},
    {"id": "restaurant",            "name": "Restaurant",       "parent_id": "restaurants",   "color": None, "role": None, "position": 1},
    {"id": "cafe_bakery",           "name": "Café / Bakery",    "parent_id": "restaurants",   "color": None, "role": None, "position": 2},
    {"id": "bar_pub",               "name": "Bar / Pub",        "parent_id": "restaurants",   "color": None, "role": None, "position": 3},
    # Subcategories — transport
    {"id": "parking",               "name": "Parking",          "parent_id": "transport",     "color": None, "role": None, "position": 0},
    {"id": "fuel",                  "name": "Fuel",             "parent_id": "transport",     "color": None, "role": None, "position": 1},
    {"id": "rideshare",             "name": "Rideshare",        "parent_id": "transport",     "color": None, "role": None, "position": 2},
    {"id": "public_transit",        "name": "Public transit",   "parent_id": "transport",     "color": None, "role": None, "position": 3},
    {"id": "train_station",         "name": "Train",            "parent_id": "transport",     "color": None, "role": None, "position": 4},
    {"id": "tyre_service",          "name": "Tyres",            "parent_id": "transport",     "color": None, "role": None, "position": 5},
    # Subcategories — health
    {"id": "pharmacy",              "name": "Pharmacy",         "parent_id": "health",        "color": None, "role": None, "position": 0},
    {"id": "medical",               "name": "Medical",          "parent_id": "health",        "color": None, "role": None, "position": 1},
    # Subcategories — shopping
    {"id": "online",                "name": "Online",           "parent_id": "shopping",      "color": None, "role": None, "position": 0},
    {"id": "clothing",              "name": "Clothing",         "parent_id": "shopping",      "color": None, "role": None, "position": 1},
    {"id": "electronics",           "name": "Electronics",      "parent_id": "shopping",      "color": None, "role": None, "position": 2},
    {"id": "general",               "name": "General",          "parent_id": "shopping",      "color": None, "role": None, "position": 3},
    # Subcategories — entertainment
    {"id": "cinema",                "name": "Cinema",           "parent_id": "entertainment", "color": None, "role": None, "position": 0},
    {"id": "events",                "name": "Events",           "parent_id": "entertainment", "color": None, "role": None, "position": 1},
    {"id": "gaming",                "name": "Gaming",           "parent_id": "entertainment", "color": None, "role": None, "position": 2},
    # Subcategories — transfers
    {"id": "rent_contribution",     "name": "Rent contribution","parent_id": "transfers",     "color": None, "role": None, "position": 0},
    {"id": "bizum_out",             "name": "Bizum out",        "parent_id": "transfers",     "color": None, "role": None, "position": 1},
    {"id": "transfer_out",          "name": "Transfer out",     "parent_id": "transfers",     "color": None, "role": None, "position": 2},
    # Subcategories — cash
    {"id": "atm_withdrawal",        "name": "ATM withdrawal",   "parent_id": "cash",          "color": None, "role": None, "position": 0},
    # Subcategories — admin
    {"id": "city_tax",              "name": "City tax",         "parent_id": "admin",         "color": None, "role": None, "position": 0},
    {"id": "travel_tickets",        "name": "Travel tickets",   "parent_id": "admin",         "color": None, "role": None, "position": 1},
    # Subcategories — uncategorized
    {"id": "other",                 "name": "Other",            "parent_id": "uncategorized", "color": None, "role": None, "position": 0},
]


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

                CREATE TABLE IF NOT EXISTS categories (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    parent_id  TEXT REFERENCES categories(id),
                    color      TEXT,
                    role       TEXT,
                    position   INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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

                CREATE INDEX IF NOT EXISTS idx_tx_month    ON transactions(month);
                CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
                CREATE INDEX IF NOT EXISTS idx_tx_bank     ON transactions(bank_id);
                CREATE INDEX IF NOT EXISTS idx_cat_parent  ON categories(parent_id);
                CREATE INDEX IF NOT EXISTS idx_hsh_date    ON health_score_history(recorded_at);
            """)
        self._migrate_schema()
        self._seed_categories()

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
    # ------------------------------------------------------------------
    # Categories — seed
    # ------------------------------------------------------------------

    def _seed_categories(self) -> None:
        """Populate the categories table from _DEFAULT_CATEGORIES if it is empty."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            if count > 0:
                return
            conn.executemany(
                """INSERT OR IGNORE INTO categories (id, name, parent_id, color, role, position)
                   VALUES (:id, :name, :parent_id, :color, :role, :position)""",
                _DEFAULT_CATEGORIES,
            )

    # ------------------------------------------------------------------
    # Categories — read
    # ------------------------------------------------------------------

    def get_categories(self) -> list[dict]:
        """
        Returns the full category tree as a flat list of dicts.
        Each dict has: id, name, parent_id, color, role, position, created_at.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, name, parent_id, color, role, position, created_at
                   FROM categories
                   ORDER BY CASE WHEN parent_id IS NULL THEN 0 ELSE 1 END, position, id"""
            ).fetchall()
        cols = ["id", "name", "parent_id", "color", "role", "position", "created_at"]
        return [dict(zip(cols, r)) for r in rows]

    def get_categories_by_role(self, role: str) -> list[str]:
        """Returns top-level category ids with a given role (for health engine)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM categories WHERE parent_id IS NULL AND role = ?",
                (role,),
            ).fetchall()
        return [r[0] for r in rows]

    def get_category_by_id(self, cat_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, parent_id, color, role, position, created_at FROM categories WHERE id = ?",
                (cat_id,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(["id", "name", "parent_id", "color", "role", "position", "created_at"], row))

    # ------------------------------------------------------------------
    # Categories — write
    # ------------------------------------------------------------------

    def create_category(
        self,
        cat_id: str,
        name: str,
        parent_id: str | None = None,
        color: str | None = None,
        role: str | None = None,
        position: int = 0,
    ) -> dict:
        """Insert a new category. Raises ValueError if id already exists."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM categories WHERE id = ?", (cat_id,)
            ).fetchone()
            if existing:
                raise ValueError(f"Category id '{cat_id}' already exists.")
            conn.execute(
                """INSERT INTO categories (id, name, parent_id, color, role, position)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cat_id, name, parent_id, color, role, position),
            )
        return self.get_category_by_id(cat_id)

    def update_category(
        self,
        cat_id: str,
        name: str | None = None,
        color: str | None = None,
        role: str | None = None,
        position: int | None = None,
    ) -> dict | None:
        """Partial update of a category. Returns the updated dict or None if not found."""
        cat = self.get_category_by_id(cat_id)
        if not cat:
            return None
        new_name = name if name is not None else cat["name"]
        new_color = color if color is not None else cat["color"]
        new_role = role if role is not None else cat["role"]
        new_position = position if position is not None else cat["position"]
        with self._connect() as conn:
            conn.execute(
                """UPDATE categories SET name=?, color=?, role=?, position=? WHERE id=?""",
                (new_name, new_color, new_role, new_position, cat_id),
            )
        return self.get_category_by_id(cat_id)

    def delete_category(self, cat_id: str) -> dict:
        """
        Delete a category and all its subcategories.
        Transactions referencing deleted categories are set to NULL.
        Returns counts of deleted categories and affected transactions.
        """
        with self._connect() as conn:
            # Collect all ids to delete (the category itself + its children)
            child_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM categories WHERE parent_id = ?", (cat_id,)
                ).fetchall()
            ]
            all_ids = [cat_id] + child_ids

            # Null out transactions for all affected category ids
            affected = 0
            for cid in all_ids:
                r = conn.execute(
                    "UPDATE transactions SET category = NULL, subcategory = NULL, category_source = NULL "
                    "WHERE category = ? OR subcategory = ?",
                    (cid, cid),
                )
                affected += r.rowcount

            # Delete subcategories first (FK children), then parent
            for cid in child_ids:
                conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))

        return {
            "deleted_categories": len(all_ids),
            "affected_transactions": affected,
        }

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
                           clean_description        = CASE WHEN clean_description_source = 'manual' THEN clean_description ELSE ? END,
                           clean_description_source = CASE WHEN clean_description_source = 'manual' THEN 'manual' ELSE ? END,
                           stripped_description     = CASE WHEN clean_description_source = 'manual' THEN stripped_description ELSE ? END
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
        """Returns id + description + stripped_description for every transaction — used by recategorize."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, description, stripped_description FROM transactions ORDER BY date DESC"
            ).fetchall()
        return [{"id": r[0], "description": r[1], "stripped_description": r[2]} for r in rows]

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

            # Leisure = all categories with role='leisure'
            leisure_row = conn.execute("""
                SELECT COALESCE(SUM(ABS(t.amount)), 0)
                FROM transactions t
                JOIN categories c ON t.category = c.id
                WHERE t.month = ? AND t.is_reversal = 0
                  AND t.amount < 0
                  AND c.role = 'leisure'
                  AND c.parent_id IS NULL
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
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
