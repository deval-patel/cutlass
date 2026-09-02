"""Persistence for timeline documents and their version history (Plan 1).

Every write creates an immutable version row; the timelines row points at
the current document. Editing never loses history.
"""

import sqlite3
import uuid
from typing import Any

from ..db import connections
from ..timelines.schema import Timeline, validate


def _execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    conn = connections.connect()
    try:
        with conn:
            conn.execute(sql, params)
    finally:
        conn.close()


def _query_all(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = connections.connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def get_timeline(project_id: str, name: str = "main") -> tuple[str, int, Timeline] | None:
    """Returns (timeline_id, version, document) or None."""
    rows = _query_all(
        "SELECT id, version, document FROM timelines WHERE project_id = ? AND name = ?",
        (project_id, name),
    )
    if not rows:
        return None
    row = rows[0]
    return row["id"], row["version"], Timeline.model_validate_json(row["document"])


def save_timeline(
    project_id: str, document: Timeline, label: str | None = None, name: str = "main"
) -> tuple[str, int]:
    """Create or update the project's timeline, recording a version.

    Validates the document first — invalid timelines never reach storage.
    Returns (timeline_id, new_version).
    """
    validate(document)
    conn = connections.connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT id, version FROM timelines WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()
            if row is None:
                timeline_id = uuid.uuid4().hex[:12]
                conn.execute(
                    "INSERT INTO timelines (id, project_id, name, document, version) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (timeline_id, project_id, name, document.model_dump_json()),
                )
                conn.execute(
                    "INSERT INTO timeline_versions (id, timeline_id, version, label, document) "
                    "VALUES (?, ?, 1, ?, ?)",
                    (uuid.uuid4().hex[:12], timeline_id, label, document.model_dump_json()),
                )
                return timeline_id, 1
            timeline_id, current = row["id"], row["version"]
            new_version = current + 1
            conn.execute(
                "UPDATE timelines SET document = ?, version = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (document.model_dump_json(), new_version, timeline_id),
            )
            conn.execute(
                "INSERT INTO timeline_versions (id, timeline_id, version, label, document) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex[:12],
                    timeline_id,
                    new_version,
                    label,
                    document.model_dump_json(),
                ),
            )
            return timeline_id, new_version
    finally:
        conn.close()


def list_versions(project_id: str, name: str = "main") -> list[dict[str, str | int | None]]:
    rows = _query_all(
        """
        SELECT v.version, v.label, v.created_at
        FROM timeline_versions v JOIN timelines t ON t.id = v.timeline_id
        WHERE t.project_id = ? AND t.name = ?
        ORDER BY v.version DESC
        """,
        (project_id, name),
    )
    return [
        {"version": row["version"], "label": row["label"], "created_at": row["created_at"]}
        for row in rows
    ]


def restore_version(
    project_id: str, version: int, name: str = "main"
) -> tuple[int, Timeline] | None:
    """Restore an old version as the new current document (new version number).

    Returns (new_version, document) or None if the version doesn't exist.
    """
    rows = _query_all(
        """
        SELECT v.document
        FROM timeline_versions v JOIN timelines t ON t.id = v.timeline_id
        WHERE t.project_id = ? AND t.name = ? AND v.version = ?
        """,
        (project_id, name, version),
    )
    if not rows:
        return None
    document = Timeline.model_validate_json(rows[0]["document"])
    _, new_version = save_timeline(project_id, document, label=f"restore of v{version}", name=name)
    return new_version, document
