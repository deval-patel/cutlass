"""The /api/v1 surface: projects, assets, and timeline documents."""

import re
import uuid
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..models import Asset, Project, ProjectSummary
from ..repositories import assets as assets_repo
from ..repositories import projects as projects_repo
from ..repositories import timelines as timelines_repo
from ..services import analyzer
from ..services.ingest import ingest_upload
from ..services.queue import get_queue
from ..timelines.schema import Timeline, TimelineInfo, validate

router = APIRouter(prefix="/api/v1")

_FRAME_NAME = re.compile(r"^frame_\d{6}\.jpg$")


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectDetail(BaseModel):
    project: Project
    assets: list[Asset]
    timeline: TimelineInfo | None = None


def _get_project(project_id: str) -> Project:
    project = projects_repo.get_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def _get_asset(asset_id: str) -> Asset:
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    asset.has_render = analyzer.render_path(asset_id).exists()
    return asset


@router.post("/projects")
def create_project(body: CreateProjectRequest) -> Project:
    project_id = uuid.uuid4().hex[:12]
    projects_repo.create_project(project_id, body.name)
    created = projects_repo.get_project(project_id)
    assert created is not None  # just inserted
    return created


@router.get("/projects")
def list_projects(limit: int = 50, offset: int = 0) -> list[ProjectSummary]:
    limit = max(1, min(limit, 200))
    return projects_repo.list_projects(limit=limit, offset=max(0, offset))


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> ProjectDetail:
    project = _get_project(project_id)
    assets = assets_repo.list_assets(project_id)
    for asset in assets:
        asset.has_render = analyzer.render_path(asset.id).exists()
    timeline: TimelineInfo | None = None
    try:
        timeline_id, version, document = analyzer.get_or_seed_timeline(project_id)
        timeline = TimelineInfo(
            id=timeline_id,
            project_id=project_id,
            name="main",
            version=version,
            document=document,
        )
    except RuntimeError:
        # No timeline yet and not seedable (no/ambiguous draft) — that's a
        # valid state for a fresh project.
        pass
    return ProjectDetail(project=project, assets=assets, timeline=timeline)


@router.post("/projects/{project_id}/assets")
async def upload_asset(project_id: str, video: UploadFile = File(...)) -> Asset:
    _get_project(project_id)
    asset_id = await ingest_upload(video, project_id=project_id)
    return _get_asset(asset_id)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> Asset:
    return _get_asset(asset_id)


@router.get("/assets/{asset_id}/frames")
def list_frames(asset_id: str) -> list[dict[str, Any]]:
    if assets_repo.get_asset(asset_id) is None:
        raise HTTPException(404, "asset not found")
    return analyzer.frames_manifest(asset_id)


@router.get("/assets/{asset_id}/frames/{name}")
def get_frame(asset_id: str, name: str) -> FileResponse:
    if not _FRAME_NAME.match(name):
        raise HTTPException(400, "invalid frame name")
    path = analyzer.asset_dir(asset_id) / "frames" / name
    if not path.exists():
        raise HTTPException(404, "frame not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/assets/{asset_id}/source")
def get_source(asset_id: str) -> FileResponse:
    path = analyzer.source_path(asset_id)
    if not path.exists():
        raise HTTPException(404, "source not found")
    return FileResponse(path, media_type="video/mp4")


@router.get("/assets/{asset_id}/render")
def get_render(asset_id: str) -> FileResponse:
    path = analyzer.render_path(asset_id)
    if not path.exists():
        raise HTTPException(404, "render not found")
    return FileResponse(path, media_type="video/mp4", filename="final_cut.mp4")


@router.post("/assets/{asset_id}/render")
def start_render(asset_id: str) -> dict[str, str]:
    if assets_repo.get_asset(asset_id) is None:
        raise HTTPException(404, "asset not found")
    if analyzer.render_path(asset_id).exists():
        return {"status": "already rendered"}
    get_queue().enqueue("render", asset_id)
    return {"status": "rendering"}


@router.get("/projects/{project_id}/timeline")
def get_timeline(project_id: str) -> TimelineInfo:
    _get_project(project_id)
    try:
        timeline_id, version, document = analyzer.get_or_seed_timeline(project_id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return TimelineInfo(
        id=timeline_id, project_id=project_id, name="main", version=version, document=document
    )


@router.put("/projects/{project_id}/timeline")
def update_timeline(project_id: str, document: Timeline = Body(...)) -> TimelineInfo:
    _get_project(project_id)
    try:
        validate(document)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    timeline_id, version = timelines_repo.save_timeline(project_id, document, label="api edit")
    return TimelineInfo(
        id=timeline_id,
        project_id=project_id,
        name="main",
        version=version,
        document=document,
    )


@router.get("/projects/{project_id}/timeline/versions")
def list_timeline_versions(project_id: str) -> list[dict[str, Any]]:
    _get_project(project_id)
    return timelines_repo.list_versions(project_id)


@router.post("/projects/{project_id}/timeline/versions/{version}/restore")
def restore_timeline_version(project_id: str, version: int) -> TimelineInfo:
    _get_project(project_id)
    restored = timelines_repo.restore_version(project_id, version)
    if restored is None:
        raise HTTPException(404, f"version {version} not found")
    new_version, document = restored
    timeline_id, _, _ = analyzer.get_or_seed_timeline(project_id)
    return TimelineInfo(
        id=timeline_id,
        project_id=project_id,
        name="main",
        version=new_version,
        document=document,
    )
