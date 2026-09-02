import json
import sqlite3

from .config import DB_PATH
from .models import JobStatus, Segment, VideoMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    meta TEXT,
    segments TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)


def _row_to_job(row: sqlite3.Row) -> JobStatus:
    meta = VideoMeta.model_validate_json(row["meta"]) if row["meta"] else None
    segments = (
        [Segment.model_validate(s) for s in json.loads(row["segments"])]
        if row["segments"]
        else []
    )
    return JobStatus(
        id=row["id"],
        filename=row["filename"],
        status=row["status"],
        error=row["error"],
        meta=meta,
        segments=segments,
        has_render=False,
        created_at=row["created_at"],
    )


def list_jobs() -> list[JobStatus]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC").fetchall()
    return [_row_to_job(row) for row in rows]


def create_job(job_id: str, filename: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, filename) VALUES (?, ?)", (job_id, filename)
        )


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


def get_job(job_id: str) -> JobStatus | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row is not None else None
