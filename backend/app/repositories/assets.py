"""Persistence for assets — an ingested source file and its analysis.

The pre-Plan-1 'job' becomes an asset: probe metadata, frame notes,
transcript, draft EDL. All SQL for the assets table lives here.
"""

import json
import sqlite3
from collections.abc import Sequence
from typing import Any, cast

from ..db import connections
from ..events import JobEvent, get_broker
from ..models import Asset, FrameNote, JobStatusValue, Segment, TranscriptLine, VideoMeta


def _execute(sql: str, params: Sequence[Any] = ()) -> None:
    conn = connections.connect()
    try:
        with conn:
            conn.execute(sql, tuple(params))
    finally:
        conn.close()


def _query_all(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    conn = connections.connect()
    try:
        return conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()


def _row_to_asset(row: sqlite3.Row) -> Asset:
    meta = VideoMeta.model_validate_json(row["meta"]) if row["meta"] else None
    segments = (
        [Segment.model_validate(s) for s in json.loads(row["segments"])] if row["segments"] else []
    )
    notes = [FrameNote.model_validate(n) for n in json.loads(row["notes"])] if row["notes"] else []
    transcript = (
        [TranscriptLine.model_validate(t) for t in json.loads(row["transcript"])]
        if row["transcript"]
        else []
    )
    return Asset(
        id=row["id"],
        project_id=row["project_id"],
        filename=row["filename"],
        status=cast(JobStatusValue, row["status"]),
        error=row["error"],
        meta=meta,
        segments=segments,
        has_render=False,
        created_at=row["created_at"],
        progress=row["progress"],
        frame_notes=notes,
        transcript=transcript,
    )


def create_asset(asset_id: str, project_id: str, filename: str) -> None:
    _execute(
        "INSERT INTO assets (id, project_id, filename) VALUES (?, ?, ?)",
        (asset_id, project_id, filename),
    )


def get_asset(asset_id: str) -> Asset | None:
    rows = _query_all("SELECT * FROM assets WHERE id = ?", (asset_id,))
    return _row_to_asset(rows[0]) if rows else None


def list_assets(project_id: str | None = None) -> list[Asset]:
    if project_id is None:
        rows = _query_all("SELECT * FROM assets ORDER BY created_at DESC, rowid DESC")
    else:
        rows = _query_all(
            "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at DESC, rowid DESC",
            (project_id,),
        )
    return [_row_to_asset(row) for row in rows]


def set_status(asset_id: str, status: str, error: str | None = None) -> None:
    if error is not None:
        _execute("UPDATE assets SET status = ?, error = ? WHERE id = ?", (status, error, asset_id))
    else:
        _execute("UPDATE assets SET status = ? WHERE id = ?", (status, asset_id))
    get_broker().publish(JobEvent(asset_id, status=status, error=error))


def set_meta(asset_id: str, meta: VideoMeta) -> None:
    _execute("UPDATE assets SET meta = ? WHERE id = ?", (meta.model_dump_json(), asset_id))


def set_segments(asset_id: str, segments: Sequence[Segment]) -> None:
    payload = json.dumps([s.model_dump() for s in segments])
    _execute("UPDATE assets SET segments = ? WHERE id = ?", (payload, asset_id))


def set_progress(asset_id: str, progress: str | None) -> None:
    _execute("UPDATE assets SET progress = ? WHERE id = ?", (progress, asset_id))
    get_broker().publish(JobEvent(asset_id, progress=progress))


def set_notes(asset_id: str, notes: Sequence[FrameNote | dict[str, Any]]) -> None:
    models = [n if isinstance(n, FrameNote) else FrameNote.model_validate(n) for n in notes]
    payload = json.dumps([n.model_dump() for n in models])
    _execute("UPDATE assets SET notes = ? WHERE id = ?", (payload, asset_id))


def set_transcript(asset_id: str, transcript: Sequence[TranscriptLine]) -> None:
    payload = json.dumps([t.model_dump() for t in transcript])
    _execute("UPDATE assets SET transcript = ? WHERE id = ?", (payload, asset_id))


def delete_all_assets() -> None:
    """Test support: wipe the table (artifact cleanup is the caller's job)."""
    _execute("DELETE FROM assets")
