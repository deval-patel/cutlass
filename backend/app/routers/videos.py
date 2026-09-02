import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..models import JobStatus, Segment
from ..repositories import jobs as jobs_repo
from ..services import analyzer, ffmpeg
from ..services.edl import normalize_segments
from ..services.queue import get_queue

router = APIRouter(prefix="/api")

EDITABLE_STATUSES = {"ready", "rendered"}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
_FRAME_NAME = re.compile(r"^frame_\d{6}\.jpg$")


def _job_payload(job_id: str) -> JobStatus:
    job = jobs_repo.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    job.has_render = analyzer.render_path(job_id).exists()
    return job


@router.post("/upload")
async def upload(video: UploadFile = File(...)) -> dict[str, str]:
    ext = Path(video.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(400, f"unsupported file type '{ext or '(none)'}' — allowed: {allowed}")

    job_id = uuid.uuid4().hex[:12]
    directory = analyzer.job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = analyzer.source_path(job_id)

    total = 0
    too_large = False
    with target.open("wb") as out:
        while chunk := await video.read(1024 * 1024):
            total += len(chunk)
            if total > config.MAX_UPLOAD_BYTES:
                too_large = True
                break
            out.write(chunk)
    if too_large:
        # Unlink only after the handle above is closed (required on Windows).
        target.unlink(missing_ok=True)
        directory.rmdir()  # fresh job dir, now empty
        raise HTTPException(413, f"file exceeds {config.MAX_UPLOAD_GB}GB limit")

    # Fail fast on files that aren't actually readable video.
    try:
        ffmpeg.probe(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "file could not be read as a video (ffprobe failed)") from exc

    jobs_repo.create_job(job_id, video.filename or "video.mp4")
    get_queue().enqueue("analyze", job_id)
    return {"id": job_id}


@router.get("/jobs")
def list_jobs() -> list[dict[str, Any]]:
    jobs = jobs_repo.list_jobs()
    for job in jobs:
        job.has_render = analyzer.render_path(job.id).exists()
    return [
        {
            "id": job.id,
            "filename": job.filename,
            "status": job.status,
            "duration_s": job.meta.duration_s if job.meta else None,
            "segments": len(job.segments),
            "has_render": job.has_render,
            "created_at": job.created_at,
        }
        for job in jobs
    ]


@router.get("/jobs/{job_id}")
def get_status(job_id: str) -> JobStatus:
    return _job_payload(job_id)


@router.put("/jobs/{job_id}/segments")
def update_segments(job_id: str, segments: list[Segment] = Body(...)) -> JobStatus:
    job = _job_payload(job_id)
    if job.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"cannot edit segments while status is '{job.status}'")
    if job.meta is None:
        raise HTTPException(409, "video metadata missing")
    normalized = normalize_segments(segments, job.meta.duration_s)
    if not normalized:
        raise HTTPException(422, "no valid segments after normalization")
    jobs_repo.set_segments(job_id, normalized)
    render = analyzer.render_path(job_id)
    if render.exists():
        render.unlink()
    jobs_repo.set_status(job_id, "ready")
    return _job_payload(job_id)


@router.get("/jobs/{job_id}/frames")
def list_frames(job_id: str) -> list[dict[str, Any]]:
    if jobs_repo.get_job(job_id) is None:
        raise HTTPException(404, "job not found")
    return analyzer.frames_manifest(job_id)


@router.get("/jobs/{job_id}/frames/{name}")
def get_frame(job_id: str, name: str) -> FileResponse:
    if not _FRAME_NAME.match(name):
        raise HTTPException(400, "invalid frame name")
    path = analyzer.job_dir(job_id) / "frames" / name
    if not path.exists():
        raise HTTPException(404, "frame not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/jobs/{job_id}/source")
def get_source(job_id: str) -> FileResponse:
    path = analyzer.source_path(job_id)
    if not path.exists():
        raise HTTPException(404, "source not found")
    return FileResponse(path, media_type="video/mp4")


@router.get("/jobs/{job_id}/render")
def get_render(job_id: str) -> FileResponse:
    path = analyzer.render_path(job_id)
    if not path.exists():
        raise HTTPException(404, "render not found")
    return FileResponse(path, media_type="video/mp4", filename="final_cut.mp4")


@router.post("/jobs/{job_id}/render")
def start_render(job_id: str) -> dict[str, str]:
    if jobs_repo.get_job(job_id) is None:
        raise HTTPException(404, "job not found")
    if analyzer.render_path(job_id).exists():
        return {"status": "already rendered"}
    get_queue().enqueue("render", job_id)
    return {"status": "rendering"}
