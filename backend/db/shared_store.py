"""
db/shared_store.py — SQLite store for shared data across all users.

Currently stores:
  - description_rules: clean_description rules (label + patterns), shared
    between all users and all bank imports. Replaces clean_description_rules.yaml
    as the source of truth.

DB path: data/shared.db (configurable via Settings.shared_db_path)

Migration: on first startup, if the table is empty and the legacy YAML exists,
rules are imported automatically (one-shot, non-destructive).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS description_rules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    label      TEXT NOT NULL UNIQUE,
                    patterns   TEXT NOT NULL,          -- JSON array of regex strings
                    position   INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rules_position
                ON description_rules(position)
            """)

    # ------------------------------------------------------------------
    # YAML migration (one-shot)
    # ------------------------------------------------------------------

    def migrate_from_yaml(self, yaml_path: Path) -> int:
        """
        Import rules from a YAML file into the DB if the table is currently empty.
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

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all_rules(self) -> list[dict]:
        """Returns all rules ordered by position, as list of {label, patterns: [str]}."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT label, patterns, position FROM description_rules ORDER BY position ASC"
            ).fetchall()
        return [
            {"label": row["label"], "patterns": json.loads(row["patterns"])}
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
    # Write
    # ------------------------------------------------------------------

    def create_rule(self, label: str, patterns: list[str], position: int | None = None) -> dict:
        """
        Insert a new rule. If position is None, appends at the end.
        Raises ValueError if label already exists.
        """
        if self.rule_exists(label):
            raise ValueError(f"Rule '{label}' already exists.")
        pos = position if position is not None else self.get_max_position() + 1
        with self._connect() as conn:
            # Shift existing rules down to make room if inserting mid-list
            if position is not None:
                conn.execute(
                    "UPDATE description_rules SET position = position + 1 WHERE position >= ?",
                    (pos,),
                )
            conn.execute(
                """INSERT INTO description_rules (label, patterns, position)
                   VALUES (?, ?, ?)""",
                (label, json.dumps(patterns), pos),
            )
        return {"label": label, "patterns": patterns}

    def update_rule(
        self,
        label: str,
        new_label: str | None = None,
        patterns: list[str] | None = None,
    ) -> dict | None:
        """
        Update label and/or patterns for an existing rule.
        Returns the updated rule dict, or None if not found.
        Raises ValueError if new_label already exists (and differs from label).
        """
        if not self.rule_exists(label):
            return None

        final_label = new_label if new_label and new_label != label else label

        if final_label != label and self.rule_exists(final_label):
            raise ValueError(f"Rule '{final_label}' already exists.")

        with self._connect() as conn:
            if patterns is not None and final_label != label:
                conn.execute(
                    """UPDATE description_rules
                       SET label = ?, patterns = ?, updated_at = datetime('now')
                       WHERE label = ?""",
                    (final_label, json.dumps(patterns), label),
                )
            elif patterns is not None:
                conn.execute(
                    """UPDATE description_rules
                       SET patterns = ?, updated_at = datetime('now')
                       WHERE label = ?""",
                    (json.dumps(patterns), label),
                )
            elif final_label != label:
                conn.execute(
                    """UPDATE description_rules
                       SET label = ?, updated_at = datetime('now')
                       WHERE label = ?""",
                    (final_label, label),
                )

        # Fetch updated row
        with self._connect() as conn:
            row = conn.execute(
                "SELECT label, patterns FROM description_rules WHERE label = ?",
                (final_label,),
            ).fetchone()

        if not row:
            return None
        return {"label": row["label"], "patterns": json.loads(row["patterns"])}

    def delete_rule(self, label: str) -> bool:
        """Delete a rule by label. Returns True if deleted, False if not found."""
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM description_rules WHERE label = ?", (label,)
            )
        return result.rowcount > 0
