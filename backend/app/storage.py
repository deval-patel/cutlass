import contextlib
import json
import sqlite3
from collections.abc import Sequence
from typing import Any, cast

from .config import DB_PATH
from .models import FrameNote, JobStatus, JobStatusValue, Segment, TranscriptLine, VideoMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    meta TEXT,
    segments TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    progress TEXT,
    notes TEXT,
    transcript TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)
        # Migrate DBs created before these columns existed.
        for col in ("progress", "notes", "transcript"):
            with contextlib.suppress(sqlite3.OperationalError):  # column already present
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")


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


def list_jobs() -> list[JobStatus]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC").fetchall()
    return [_row_to_job(row) for row in rows]


def create_job(job_id: str, filename: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO jobs (id, filename) VALUES (?, ?)", (job_id, filename))


def set_status(job_id: str, status: str, error: str | None = None) -> None:
    with _connect() as conn:
        if error is not None:
            conn.execute(
                "UPDATE jobs SET status = ?, error = ? WHERE id = ?", (status, error, job_id)
            )
        else:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def set_meta(job_id: str, meta: VideoMeta) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET meta = ? WHERE id = ?", (meta.model_dump_json(), job_id))


def set_segments(job_id: str, segments: list[Segment]) -> None:
    payload = json.dumps([s.model_dump() for s in segments])
    with _connect() as conn:
        conn.execute("UPDATE jobs SET segments = ? WHERE id = ?", (payload, job_id))


def set_progress(job_id: str, progress: str | None) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id))


def set_notes(job_id: str, notes: Sequence[FrameNote | dict[str, Any]]) -> None:
    models = [n if isinstance(n, FrameNote) else FrameNote.model_validate(n) for n in notes]
    payload = json.dumps([n.model_dump() for n in models])
    with _connect() as conn:
        conn.execute("UPDATE jobs SET notes = ? WHERE id = ?", (payload, job_id))


def set_transcript(job_id: str, transcript: list[TranscriptLine]) -> None:
    payload = json.dumps([t.model_dump() for t in transcript])
    with _connect() as conn:
        conn.execute("UPDATE jobs SET transcript = ? WHERE id = ?", (payload, job_id))


def get_job(job_id: str) -> JobStatus | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row is not None else None
