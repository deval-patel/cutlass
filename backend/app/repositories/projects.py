"""Persistence for projects (Plan 1)."""

import sqlite3
from typing import Any

from ..db import connections
from ..models import Project, ProjectSummary


def _query_all(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = connections.connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    conn = connections.connect()
    try:
        with conn:
            conn.execute(sql, params)
    finally:
        conn.close()


def create_project(project_id: str, name: str, user_id: str | None = None) -> None:
    _execute(
        "INSERT INTO projects (id, name, user_id) VALUES (?, ?, ?)",
        (project_id, name, user_id),
    )


def get_project(project_id: str) -> Project | None:
    rows = _query_all("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not rows:
        return None
    row = rows[0]
    return Project(
        id=row["id"], name=row["name"], user_id=row["user_id"], created_at=row["created_at"]
    )


def list_projects(limit: int = 50, offset: int = 0) -> list[ProjectSummary]:
    """Newest first, with asset counts and total duration for the list view."""
    rows = _query_all(
        """
        SELECT p.id, p.name, p.created_at,
               COUNT(a.id) AS asset_count,
               MAX(CAST(json_extract(a.meta, '$.duration_s') AS REAL)) AS duration_s,
               (SELECT t.id FROM timelines t WHERE t.project_id = p.id LIMIT 1) AS timeline_id
        FROM projects p
        LEFT JOIN assets a ON a.project_id = p.id
        GROUP BY p.id
        ORDER BY p.created_at DESC, p.rowid DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    return [
        ProjectSummary(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            assets=row["asset_count"],
            duration_s=row["duration_s"],
            timeline_id=row["timeline_id"],
        )
        for row in rows
    ]


def delete_project(project_id: str) -> bool:
    """Cascades to assets/timelines via FK. Returns False if unknown id."""
    conn = connections.connect()
    try:
        with conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def delete_all_projects() -> None:
    """Test support: wipe projects (cascades to assets/timelines/versions)."""
    _execute("DELETE FROM projects")
