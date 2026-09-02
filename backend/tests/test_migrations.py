"""Migration runner contract (ADR-0003): fresh DBs, legacy DBs, idempotency."""

import sqlite3
from pathlib import Path

from app.db import connections, migrations


def _expected_versions() -> list[str]:
    return sorted(path.stem.split("_", 1)[0] for path in migrations.MIGRATIONS_DIR.glob("*.sql"))


def _jobs_columns(db: Path) -> set[str]:
    conn = connections.connect(db)
    try:
        return {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    finally:
        conn.close()


def test_fresh_database_applies_all_migrations(tmp_path: Path):
    db = tmp_path / "fresh.db"
    applied = migrations.ensure_current(db)
    assert applied == _expected_versions()
    assert "user_id" in _jobs_columns(db)


def test_ensure_current_is_idempotent(tmp_path: Path):
    db = tmp_path / "fresh.db"
    migrations.ensure_current(db)
    assert migrations.ensure_current(db) == []


def test_legacy_database_is_stamped_and_upgraded(tmp_path: Path):
    # A database created before the runner existed: jobs table, no history.
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        (migrations.MIGRATIONS_DIR / "0001_baseline_jobs.sql").read_text(encoding="utf-8")
    )
    conn.commit()
    conn.close()

    applied = migrations.ensure_current(db)
    assert applied == _expected_versions()[1:]  # baseline stamped, only deltas run
    assert "user_id" in _jobs_columns(db)
    assert migrations.ensure_current(db) == []
