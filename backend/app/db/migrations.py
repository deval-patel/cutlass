"""Ordered SQL migrations (ADR-0003).

Files in ``migrations/`` apply in filename order; the schema_migrations
table records what has run. Databases created before this runner existed
are stamped with the baseline (0001) — their schema *is* the baseline —
and upgraded from there. Applying is idempotent.
"""

import logging
import sqlite3
from pathlib import Path

from . import connections

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_BASELINE_VERSION = "0001"

_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _version_of(path: Path) -> str:
    """Migration identity is the numeric filename prefix (e.g. '0002')."""
    return path.stem.split("_", 1)[0]


def ensure_current(db_path: Path | None = None) -> list[str]:
    """Bring the schema up to date; returns the versions applied this call."""
    conn = connections.connect(db_path)
    try:
        conn.execute(_SCHEMA_MIGRATIONS_SQL)
        conn.commit()
        done = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        if not done and _table_exists(conn, "jobs"):
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (_BASELINE_VERSION,))
            conn.commit()
            done.add(_BASELINE_VERSION)
        applied: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = _version_of(path)
            if version in done:
                continue
            logger.info("applying migration %s", path.stem)
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.commit()
            applied.append(version)
        return applied
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None
