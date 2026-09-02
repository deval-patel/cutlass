"""Legacy /api endpoints — a compatibility shim over the Plan 1 domain.

The pre-Plan-1 API spoke of 'jobs'; jobs are now assets (ids preserved by
the cutover migration). These endpoints keep the exact legacy shapes so
the existing frontend keeps working; new code builds on /api/v1.
"""

import re
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..models import Asset, Segment
from ..repositories import assets as assets_repo
from ..services import analyzer
from ..services.edl import normalize_segments
from ..services.ingest import ingest_upload
from ..services.queue import get_queue

router = APIRouter(prefix="/api")

EDITABLE_STATUSES = {"ready", "rendered"}
_FRAME_NAME = re.compile(r"^frame_\d{6}\.jpg$")


def _asset_payload(asset_id: str) -> Asset:
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "job not found")
    asset.has_render = analyzer.render_path(asset_id).exists()
    return asset


@router.post("/upload")
async def upload(video: UploadFile = File(...)) -> dict[str, str]:
    asset_id = await ingest_upload(video)
    return {"id": asset_id}


@router.get("/jobs")
def list_jobs() -> list[dict[str, Any]]:
    assets = assets_repo.list_assets()
    for asset in assets:
        asset.has_render = analyzer.render_path(asset.id).exists()
    return [
        {
            "id": asset.id,
            "filename": asset.filename,
            "status": asset.status,
            "duration_s": asset.meta.duration_s if asset.meta else None,
            "segments": len(asset.segments),
            "has_render": asset.has_render,
            "created_at": asset.created_at,
        }
        for asset in assets
    ]


@router.get("/jobs/{job_id}")
def get_status(job_id: str) -> Asset:
    return _asset_payload(job_id)


@router.put("/jobs/{job_id}/segments")
def update_segments(job_id: str, segments: list[Segment] = Body(...)) -> Asset:
    asset = _asset_payload(job_id)
    if asset.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"cannot edit segments while status is '{asset.status}'")
    if asset.meta is None:
        raise HTTPException(409, "video metadata missing")
    if len(assets_repo.list_assets(asset.project_id)) != 1:
        raise HTTPException(409, "multi-asset projects edit the timeline via /api/v1")
    normalized = normalize_segments(segments, asset.meta.duration_s)
    if not normalized:
        raise HTTPException(422, "no valid segments after normalization")
    assets_repo.set_segments(job_id, normalized)
    analyzer.sync_timeline_from_draft(job_id)
    render = analyzer.render_path(job_id)
    if render.exists():
        render.unlink()
    assets_repo.set_status(job_id, "ready")
    return _asset_payload(job_id)


@router.get("/jobs/{job_id}/frames")
def list_frames(job_id: str) -> list[dict[str, Any]]:
    if assets_repo.get_asset(job_id) is None:
        raise HTTPException(404, "job not found")
    return analyzer.frames_manifest(job_id)


@router.get("/jobs/{job_id}/frames/{name}")
def get_frame(job_id: str, name: str) -> FileResponse:
    if not _FRAME_NAME.match(name):
        raise HTTPException(400, "invalid frame name")
    path = analyzer.asset_dir(job_id) / "frames" / name
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
    if assets_repo.get_asset(job_id) is None:
        raise HTTPException(404, "job not found")
    if analyzer.render_path(job_id).exists():
        return {"status": "already rendered"}
    get_queue().enqueue("render", job_id)
    return {"status": "rendering"}
