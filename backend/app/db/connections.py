"""SQLite connection factory — every database handle in the app comes from here.

Centralizing this lets us enforce per-connection pragmas everywhere:
WAL + busy_timeout so concurrent workers never hit 'database is locked',
and foreign-key enforcement (SQLite disables it by default).
"""

import sqlite3
from pathlib import Path

from ..config import DB_PATH


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
