"""Migration runner contract (ADR-0003): fresh DBs, legacy DBs, idempotency."""

import sqlite3
from pathlib import Path

from app.db import connections, migrations


def _expected_versions() -> list[str]:
    return sorted(path.stem.split("_", 1)[0] for path in migrations.MIGRATIONS_DIR.glob("*.sql"))


def _tables(db: Path) -> set[str]:
    conn = connections.connect(db)
    try:
        return {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()


def _columns(db: Path, table: str) -> set[str]:
    conn = connections.connect(db)
    try:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_fresh_database_applies_all_migrations(tmp_path: Path):
    db = tmp_path / "fresh.db"
    applied = migrations.ensure_current(db)
    assert applied == _expected_versions()
    # End-state schema: the domain tables exist with the multi-user seam,
    # and the pre-Plan-1 jobs table is gone (cutover migration).
    assert {"projects", "assets", "timelines", "timeline_versions"} <= _tables(db)
    assert "user_id" in _columns(db, "assets")
    assert "jobs" not in _tables(db)


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
    assert "user_id" in _columns(db, "assets")
    assert "jobs" not in _tables(db)
    assert migrations.ensure_current(db) == []


def test_legacy_jobs_become_project_assets(tmp_path: Path):
    """The cutover migration preserves data: one job -> project + asset."""
    db = tmp_path / "legacy-data.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        (migrations.MIGRATIONS_DIR / "0001_baseline_jobs.sql").read_text(encoding="utf-8")
    )
    conn.execute(
        "INSERT INTO jobs (id, filename, status, segments) VALUES (?, ?, ?, ?)",
        (
            "legacy1",
            "trip.mp4",
            "ready",
            '[{"start_s": 1.0, "end_s": 4.0, "reason": "r", "confidence": 1.0}]',
        ),
    )
    conn.commit()
    conn.close()

    migrations.ensure_current(db)

    conn = connections.connect(db)
    try:
        project = conn.execute("SELECT id, name FROM projects").fetchone()
        assert project["id"] == "p-legacy1"
        assert project["name"] == "trip.mp4"
        asset = conn.execute("SELECT * FROM assets WHERE id = 'legacy1'").fetchone()
        assert asset["project_id"] == "p-legacy1"
        assert asset["status"] == "ready"
        assert "start_s" in asset["segments"]
    finally:
        conn.close()
