"""
db/user_store.py — SQLite persistence for user accounts.

Users are stored in a dedicated 'auth.db' file, separate from the per-user
finance databases. This allows auth to work independently of finance data.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path


class UserStore:
    """Manages the users table in the shared auth.db database."""

    def __init__(self, auth_db_path: str | Path = "data/auth.db"):
        self._db_path = Path(auth_db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id          TEXT PRIMARY KEY,
                    email       TEXT UNIQUE NOT NULL,
                    hashed_pw   TEXT NOT NULL,
                    name        TEXT,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_user(self, email: str, hashed_pw: str, name: str | None = None) -> dict:
        """
        Insert a new user. Raises ValueError if the email is already registered.
        Returns the new user dict.
        """
        user_id = uuid.uuid4().hex
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO users (id, email, hashed_pw, name)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, email.lower().strip(), hashed_pw, name),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"Email '{email}' is already registered.")
        return self.get_user_by_id(user_id)

    def deactivate_user(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_active = 0 WHERE id = ?", (user_id,)
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, email, hashed_pw, name, is_active, created_at
                   FROM users WHERE email = ?""",
                (email.lower().strip(),),
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, email, hashed_pw, name, is_active, created_at
                   FROM users WHERE id = ?""",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, email, name, is_active, created_at FROM users ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]
