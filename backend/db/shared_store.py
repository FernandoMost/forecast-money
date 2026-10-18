"""
db/shared_store.py — SQLite store for shared data across all users.

Stores:
  - description_rules: clean_description rules (label + patterns), shared
    between all users and all bank imports. Replaces clean_description_rules.yaml
    as the source of truth.
  - categories: category taxonomy (top-level + subcategories), shared across
    all users. Replaces the per-user categories table in sqlite_store.py.
  - category_rules: regex-based categorization rules, shared across all users.
    Replaces config/category_rules.yaml as the source of truth.
  - category_suggestion_dismissed: dismissed clean_description groups for the
    category suggestion engine.

DB path: data/shared.db (configurable via Settings.shared_db_path)

Migrations (one-shot, non-destructive):
  - description_rules ← config/clean_description_rules.yaml  (legacy)
  - categories        ← _DEFAULT_CATEGORIES seed list
  - category_rules    ← config/category_rules.yaml           (legacy)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_UNSET = object()  # sentinel for "argument not provided"


class SharedStore:
    def __init__(self, db_path: str | Path = "data/shared.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS description_rules (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    label          TEXT NOT NULL UNIQUE,
                    patterns       TEXT NOT NULL,     -- JSON array of regex strings
                    category_id    TEXT,              -- optional linked category id
                    subcategory_id TEXT,              -- optional linked subcategory id
                    position       INTEGER NOT NULL DEFAULT 0,
                    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_rules_position
                ON description_rules(position);

                CREATE TABLE IF NOT EXISTS categories (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    parent_id  TEXT REFERENCES categories(id),
                    color      TEXT,
                    role       TEXT,
                    position   INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_cat_parent
                ON categories(parent_id);

                CREATE TABLE IF NOT EXISTS category_rules (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    category    TEXT NOT NULL,
                    subcategory TEXT,
                    patterns    TEXT NOT NULL,         -- JSON array of regex strings
                    position    INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_cat_rules_position
                ON category_rules(position);

                CREATE TABLE IF NOT EXISTS category_suggestion_dismissed (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    clean_description TEXT NOT NULL UNIQUE,
                    dismissed_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS ambiguous_keywords (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword    TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply incremental schema changes to existing databases."""
        with self._connect() as conn:
            existing_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(description_rules)").fetchall()
            }
            if "category_id" not in existing_cols:
                conn.execute("ALTER TABLE description_rules ADD COLUMN category_id TEXT")
            if "subcategory_id" not in existing_cols:
                conn.execute("ALTER TABLE description_rules ADD COLUMN subcategory_id TEXT")

    # ------------------------------------------------------------------
    # Ambiguous merchant keywords (opaque marketplaces: Vinted, Amazon, …)
    # ------------------------------------------------------------------
    # Purchases through marketplaces/PayPal cannot be categorized from the
    # bank statement alone — the real purchase category differs per item.
    # Keywords mark which transactions need a manual category review (see
    # the "Compras" review tab). Shared across users like the other rules.

    def seed_ambiguous_keywords(self, defaults: list[str]) -> int:
        """Insert default keywords when the table is empty. One-shot (no-op otherwise)."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM ambiguous_keywords").fetchone()[0]
            if count > 0:
                return 0
            inserted = 0
            for kw in defaults:
                if kw.strip():
                    result = conn.execute(
                        "INSERT OR IGNORE INTO ambiguous_keywords (keyword) VALUES (?)",
                        (kw.strip().upper(),),
                    )
                    inserted += result.rowcount
        return inserted

    def get_ambiguous_keywords(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, keyword, created_at FROM ambiguous_keywords ORDER BY keyword"
            ).fetchall()
        return [{"id": r[0], "keyword": r[1], "created_at": r[2]} for r in rows]

    def add_ambiguous_keyword(self, keyword: str) -> dict:
        """Add a keyword (max length 60, stored uppercased). Raises ValueError on duplicate."""
        keyword = (keyword or "").strip().upper()[:60]
        if not keyword:
            raise ValueError("Keyword cannot be empty.")
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO ambiguous_keywords (keyword) VALUES (?)", (keyword,)
                )
                row_id = cursor.lastrowid
                row = conn.execute(
                    "SELECT keyword FROM ambiguous_keywords WHERE id = ?", (row_id,)
                ).fetchone()
            except Exception as exc:
                logger.debug("Duplicate or invalid keyword '%s': %s", keyword, exc)
                raise ValueError(f"Keyword '{keyword}' already exists.")
        return {"id": row_id, "keyword": row[0]}

    def delete_ambiguous_keyword(self, keyword_id: int) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM ambiguous_keywords WHERE id = ?", (keyword_id,)
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # YAML / seed migrations (one-shot)
    # ------------------------------------------------------------------

    def migrate_from_yaml(self, yaml_path: Path) -> int:
        """
        Import description rules from a YAML file into the DB if the table is currently empty.
        Returns the number of rules imported (0 if the table already had rows).
        """
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM description_rules").fetchone()[0]
        if count > 0:
            logger.debug("description_rules table not empty (%d rows) — skipping YAML migration.", count)
            return 0

        if not yaml_path.exists():
            logger.warning("YAML migration: %s not found — starting with empty rules.", yaml_path)
            return 0

        try:
            with yaml_path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or []
        except Exception as exc:
            logger.error("YAML migration failed to parse %s: %s", yaml_path, exc)
            return 0

        imported = 0
        with self._connect() as conn:
            for pos, entry in enumerate(raw):
                label = entry.get("label", "").strip()
                patterns = entry.get("patterns", [])
                if not label or not patterns:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO description_rules (label, patterns, position)
                       VALUES (?, ?, ?)""",
                    (label, json.dumps(patterns), pos),
                )
                imported += 1

        logger.info("Migrated %d rules from %s into shared DB.", imported, yaml_path)
        return imported

    def migrate_categories_from_seed(self, default_categories: list[dict]) -> int:
        """
        Populate the categories table from a seed list if it is empty.
        Returns the number of categories inserted (0 if already populated).
        """
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count > 0:
            logger.debug("categories table not empty (%d rows) — skipping seed migration.", count)
            return 0

        with self._connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO categories (id, name, parent_id, color, role, position)
                   VALUES (:id, :name, :parent_id, :color, :role, :position)""",
                default_categories,
            )
        logger.info("Seeded %d categories into shared DB.", len(default_categories))
        return len(default_categories)

    def migrate_category_rules_from_yaml(self, yaml_path: Path) -> int:
        """
        Import category rules from config/category_rules.yaml if the table is empty.
        Returns the number of rules imported (0 if already populated).
        """
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM category_rules").fetchone()[0]
        if count > 0:
            logger.debug("category_rules table not empty (%d rows) — skipping YAML migration.", count)
            return 0

        if not yaml_path.exists():
            logger.warning("category_rules YAML migration: %s not found.", yaml_path)
            return 0

        try:
            with yaml_path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f) or []
        except Exception as exc:
            logger.error("category_rules YAML migration failed (%s): %s", yaml_path, exc)
            return 0

        imported = 0
        with self._connect() as conn:
            for pos, entry in enumerate(raw):
                category = entry.get("category", "").strip()
                subcategory = entry.get("subcategory", "").strip() or None
                patterns = entry.get("patterns", [])
                if not category or not patterns:
                    continue
                conn.execute(
                    """INSERT INTO category_rules (category, subcategory, patterns, position)
                       VALUES (?, ?, ?, ?)""",
                    (category, subcategory, json.dumps(patterns), pos),
                )
                imported += 1

        logger.info("Migrated %d category rules from %s into shared DB.", imported, yaml_path)
        return imported

    # ------------------------------------------------------------------
    # Description rules — read
    # ------------------------------------------------------------------

    def get_all_rules(self) -> list[dict]:
        """Returns all description rules ordered by position."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, label, patterns, category_id, subcategory_id, position
                   FROM description_rules ORDER BY position ASC"""
            ).fetchall()
        return [
            {
                "id": row["id"],
                "label": row["label"],
                "patterns": json.loads(row["patterns"]),
                "category_id": row["category_id"],
                "subcategory_id": row["subcategory_id"],
                "position": row["position"],
            }
            for row in rows
        ]

    def rule_exists(self, label: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM description_rules WHERE label = ?", (label,)
            ).fetchone()
        return row is not None

    def get_max_position(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM description_rules"
            ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Description rules — write
    # ------------------------------------------------------------------

    def create_rule(
        self,
        label: str,
        patterns: list[str],
        position: int | None = None,
        category_id: str | None = None,
        subcategory_id: str | None = None,
    ) -> dict:
        """
        Insert a new description rule. If position is None, appends at the end.
        Raises ValueError if label already exists.
        """
        if self.rule_exists(label):
            raise ValueError(f"Rule '{label}' already exists.")
        pos = position if position is not None else self.get_max_position() + 1
        with self._connect() as conn:
            if position is not None:
                conn.execute(
                    "UPDATE description_rules SET position = position + 1 WHERE position >= ?",
                    (pos,),
                )
            conn.execute(
                """INSERT INTO description_rules (label, patterns, category_id, subcategory_id, position)
                   VALUES (?, ?, ?, ?, ?)""",
                (label, json.dumps(patterns), category_id, subcategory_id, pos),
            )
        return {
            "label": label,
            "patterns": patterns,
            "category_id": category_id,
            "subcategory_id": subcategory_id,
        }

    def update_rule(
        self,
        label: str,
        new_label: str | None = None,
        patterns: list[str] | None = None,
        category_id: object = _UNSET,
        subcategory_id: object = _UNSET,
    ) -> dict | None:
        """
        Update label, patterns, and/or category association for an existing description rule.
        Pass category_id=None explicitly to clear the association.
        Returns the updated rule dict, or None if not found.
        Raises ValueError if new_label already exists.
        """
        if not self.rule_exists(label):
            return None

        final_label = new_label if new_label and new_label != label else label

        if final_label != label and self.rule_exists(final_label):
            raise ValueError(f"Rule '{final_label}' already exists.")

        # Fetch current values for fields not being changed
        with self._connect() as conn:
            current = conn.execute(
                "SELECT label, patterns, category_id, subcategory_id FROM description_rules WHERE label = ?",
                (label,),
            ).fetchone()

        new_patterns = json.dumps(patterns) if patterns is not None else current["patterns"]
        new_cat = category_id if category_id is not _UNSET else current["category_id"]
        new_sub = subcategory_id if subcategory_id is not _UNSET else current["subcategory_id"]

        with self._connect() as conn:
            conn.execute(
                """UPDATE description_rules
                   SET label = ?, patterns = ?, category_id = ?, subcategory_id = ?,
                       updated_at = datetime('now')
                   WHERE label = ?""",
                (final_label, new_patterns, new_cat, new_sub, label),
            )

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, label, patterns, category_id, subcategory_id FROM description_rules WHERE label = ?",
                (final_label,),
            ).fetchone()

        if not row:
            return None
        return {
            "id": row["id"],
            "label": row["label"],
            "patterns": json.loads(row["patterns"]),
            "category_id": row["category_id"],
            "subcategory_id": row["subcategory_id"],
        }

    def delete_rule(self, label: str) -> bool:
        """Delete a description rule by label. Returns True if deleted, False if not found."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM description_rules WHERE label = ?", (label,)
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Categories — read
    # ------------------------------------------------------------------

    def get_categories(self) -> list[dict]:
        """Returns the full category list ordered by level then position."""
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
        if self.get_category_by_id(cat_id):
            raise ValueError(f"Category id '{cat_id}' already exists.")
        with self._connect() as conn:
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
                """UPDATE categories
                   SET name=?, color=?, role=?, position=?, updated_at=datetime('now')
                   WHERE id=?""",
                (new_name, new_color, new_role, new_position, cat_id),
            )
        return self.get_category_by_id(cat_id)

    def delete_category(self, cat_id: str) -> dict:
        """
        Delete a category and all its subcategories.
        Returns deleted id list (callers are responsible for nulling transactions).
        """
        with self._connect() as conn:
            child_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM categories WHERE parent_id = ?", (cat_id,)
                ).fetchall()
            ]
            all_ids = [cat_id] + child_ids
            for cid in child_ids:
                conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        return {"deleted_categories": len(all_ids), "deleted_ids": all_ids}

    # ------------------------------------------------------------------
    # Category rules — read
    # ------------------------------------------------------------------

    def get_all_category_rules(self) -> list[dict]:
        """Returns all category rules ordered by position."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, category, subcategory, patterns, position, created_at
                   FROM category_rules ORDER BY position ASC"""
            ).fetchall()
        return [
            {
                "id": row["id"],
                "category": row["category"],
                "subcategory": row["subcategory"],
                "patterns": json.loads(row["patterns"]),
                "position": row["position"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_category_rule_by_id(self, rule_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, category, subcategory, patterns, position, created_at FROM category_rules WHERE id = ?",
                (rule_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "patterns": json.loads(row["patterns"]),
            "position": row["position"],
            "created_at": row["created_at"],
        }

    def get_max_category_rule_position(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM category_rules"
            ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Category rules — write
    # ------------------------------------------------------------------

    def create_category_rule(
        self,
        category: str,
        patterns: list[str],
        subcategory: str | None = None,
        position: int | None = None,
    ) -> dict:
        """Insert a new category rule. If position is None, appends at the end."""
        pos = position if position is not None else self.get_max_category_rule_position() + 1
        with self._connect() as conn:
            if position is not None:
                conn.execute(
                    "UPDATE category_rules SET position = position + 1 WHERE position >= ?",
                    (pos,),
                )
            cursor = conn.execute(
                """INSERT INTO category_rules (category, subcategory, patterns, position)
                   VALUES (?, ?, ?, ?)""",
                (category, subcategory, json.dumps(patterns), pos),
            )
            rule_id = cursor.lastrowid
        return self.get_category_rule_by_id(rule_id)

    def update_category_rule(
        self,
        rule_id: int,
        category: str | None = None,
        subcategory: object = _UNSET,
        patterns: list[str] | None = None,
        position: int | None = None,
    ) -> dict | None:
        """Partial update of a category rule. Returns updated dict or None if not found."""
        rule = self.get_category_rule_by_id(rule_id)
        if not rule:
            return None
        new_cat = category if category is not None else rule["category"]
        new_sub = subcategory if subcategory is not _UNSET else rule["subcategory"]
        new_pats = json.dumps(patterns) if patterns is not None else json.dumps(rule["patterns"])
        new_pos = position if position is not None else rule["position"]

        with self._connect() as conn:
            if position is not None and position != rule["position"]:
                conn.execute(
                    "UPDATE category_rules SET position = position + 1 WHERE position >= ? AND id != ?",
                    (new_pos, rule_id),
                )
            conn.execute(
                """UPDATE category_rules
                   SET category=?, subcategory=?, patterns=?, position=?, updated_at=datetime('now')
                   WHERE id=?""",
                (new_cat, new_sub, new_pats, new_pos, rule_id),
            )
        return self.get_category_rule_by_id(rule_id)

    def delete_category_rule(self, rule_id: int) -> bool:
        """Delete a category rule by id. Returns True if deleted."""
        with self._connect() as conn:
            result = conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Category suggestion dismissed
    # ------------------------------------------------------------------

    def get_dismissed_category_suggestions(self) -> set[str]:
        """Returns the set of clean_description values dismissed from category suggestions."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT clean_description FROM category_suggestion_dismissed"
            ).fetchall()
        return {r[0] for r in rows}

    def add_dismissed_category_suggestion(self, clean_description: str) -> None:
        """Permanently dismiss a clean_description from category suggestions."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO category_suggestion_dismissed (clean_description) VALUES (?)",
                (clean_description,),
            )

    def remove_dismissed_category_suggestion(self, clean_description: str) -> bool:
        """Un-dismiss a category suggestion. Returns True if removed."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM category_suggestion_dismissed WHERE clean_description = ?",
                (clean_description,),
            )
        return result.rowcount > 0
