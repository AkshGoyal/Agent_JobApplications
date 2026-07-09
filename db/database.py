"""SQLite connection + a tiny migration runner.

Migrations are numbered .sql files in db/migrations/. Applied versions are
tracked in schema_version, so running migrations is idempotent.
"""

import sqlite3
from pathlib import Path

import config


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with migrations applied and row access by name."""
    path = Path(db_path) if db_path is not None else config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[str]:
    """Apply any unapplied migrations, in filename order. Returns applied names."""
    migrations_dir = migrations_dir or config.MIGRATIONS_DIR
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
               version    TEXT PRIMARY KEY,
               applied_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    newly_applied = []
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        if sql_file.name in applied:
            continue
        conn.executescript(sql_file.read_text())
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (sql_file.name,))
        newly_applied.append(sql_file.name)
    conn.commit()
    return newly_applied
