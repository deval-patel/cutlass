"""Persistence for analysis jobs (the pre-Plan-1 'job' concept).

Every SQL statement for the jobs table lives here. Services and routers
import this module; nothing outside app/repositories touches the database.
"""

import json
import sqlite3
from collections.abc import Sequence
from typing import Any, cast

from ..db import connections
from ..models import FrameNote, JobStatus, JobStatusValue, Segment, TranscriptLine, VideoMeta


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


def _row_to_job(row: sqlite3.Row) -> JobStatus:
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
    return JobStatus(
        id=row["id"],
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


def create_job(job_id: str, filename: str) -> None:
    _execute("INSERT INTO jobs (id, filename) VALUES (?, ?)", (job_id, filename))


def get_job(job_id: str) -> JobStatus | None:
    rows = _query_all("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _row_to_job(rows[0]) if rows else None


def list_jobs() -> list[JobStatus]:
    rows = _query_all("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC")
    return [_row_to_job(row) for row in rows]


def set_status(job_id: str, status: str, error: str | None = None) -> None:
    if error is not None:
        _execute("UPDATE jobs SET status = ?, error = ? WHERE id = ?", (status, error, job_id))
    else:
        _execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def set_meta(job_id: str, meta: VideoMeta) -> None:
    _execute("UPDATE jobs SET meta = ? WHERE id = ?", (meta.model_dump_json(), job_id))


def set_segments(job_id: str, segments: Sequence[Segment]) -> None:
    payload = json.dumps([s.model_dump() for s in segments])
    _execute("UPDATE jobs SET segments = ? WHERE id = ?", (payload, job_id))


def set_progress(job_id: str, progress: str | None) -> None:
    _execute("UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id))


def set_notes(job_id: str, notes: Sequence[FrameNote | dict[str, Any]]) -> None:
    models = [n if isinstance(n, FrameNote) else FrameNote.model_validate(n) for n in notes]
    payload = json.dumps([n.model_dump() for n in models])
    _execute("UPDATE jobs SET notes = ? WHERE id = ?", (payload, job_id))


def set_transcript(job_id: str, transcript: Sequence[TranscriptLine]) -> None:
    payload = json.dumps([t.model_dump() for t in transcript])
    _execute("UPDATE jobs SET transcript = ? WHERE id = ?", (payload, job_id))


def delete_all_jobs() -> None:
    """Test support: wipe the table (artifact cleanup is the caller's job)."""
    _execute("DELETE FROM jobs")
