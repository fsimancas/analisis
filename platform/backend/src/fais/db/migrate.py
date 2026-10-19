from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path

from .connection import Database


def migration_files() -> list[Path]:
    root = files("fais.db.migrations")
    return sorted(Path(str(item)) for item in root.iterdir() if item.name.endswith(".sql"))


def migrate(database: Database) -> list[str]:
    applied_now: list[str] = []
    conn = database.connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) STRICT
            """
        )
        conn.commit()
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in migration_files():
            if path.name in applied:
                continue
            try:
                version = path.name.replace("'", "''")
                conn.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + path.read_text(encoding="utf-8")
                    + f"\nINSERT INTO schema_migrations(version) VALUES ('{version}');\n"
                    + "COMMIT;"
                )
            except sqlite3.Error as exc:
                if conn.in_transaction:
                    conn.rollback()
                raise RuntimeError(f"Migration {path.name} failed: {exc}") from exc
            applied_now.append(path.name)
    finally:
        conn.close()
    return applied_now
