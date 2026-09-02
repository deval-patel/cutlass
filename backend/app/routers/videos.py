import uuid

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import storage
from ..models import Segment
from ..services import analyzer
from ..services.edl import normalize_segments

router = APIRouter(prefix="/api")

EDITABLE_STATUSES = {"ready", "rendered"}


def _job_payload(job_id: str):
    job = storage.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    job.has_render = analyzer.render_path(job_id).exists()
    return job


@router.post("/upload")
async def upload(video: UploadFile = File(...), background: BackgroundTasks = None):
    job_id = uuid.uuid4().hex[:12]
    directory = analyzer.job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = analyzer.source_path(job_id)
    with target.open("wb") as out:
        while chunk := await video.read(1024 * 1024):
            out.write(chunk)
    storage.create_job(job_id, video.filename or "video.mp4")
    background.add_task(analyzer.run_pipeline, job_id)
    return {"id": job_id}


@router.get("/jobs/{job_id}")
def get_status(job_id: str):
    return _job_payload(job_id)


@router.put("/jobs/{job_id}/segments")
def update_segments(job_id: str, segments: list[Segment] = Body(...)):
    job = _job_payload(job_id)
    if job.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"cannot edit segments while status is '{job.status}'")
    if job.meta is None:
        raise HTTPException(409, "video metadata missing")
    normalized = normalize_segments(segments, job.meta.duration_s)
    if not normalized:
        raise HTTPException(422, "no valid segments after normalization")
    storage.set_segments(job_id, normalized)
    render = analyzer.render_path(job_id)
    if render.exists():
        render.unlink()
    storage.set_status(job_id, "ready")
    return _job_payload(job_id)


@router.get("/jobs/{job_id}/source")
def get_source(job_id: str):
    path = analyzer.source_path(job_id)
    if not path.exists():
        raise HTTPException(404, "source not found")
    return FileResponse(path, media_type="video/mp4")


@router.get("/jobs/{job_id}/render")
def get_render(job_id: str):
    path = analyzer.render_path(job_id)
    if not path.exists():
        raise HTTPException(404, "render not found")
    return FileResponse(path, media_type="video/mp4", filename="final_cut.mp4")


@router.post("/jobs/{job_id}/render")
def start_render(job_id: str, background: BackgroundTasks):
    if storage.get_job(job_id) is None:
        raise HTTPException(404, "job not found")
    if analyzer.render_path(job_id).exists():
        return {"status": "already rendered"}
    background.add_task(analyzer.run_render, job_id)
    return {"status": "rendering"}
