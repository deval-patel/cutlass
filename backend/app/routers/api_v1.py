"""The /api/v1 surface: projects, assets, and timeline documents."""

import re
import shutil
import uuid
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ..models import Asset, Project, ProjectSummary, TranscriptLine
from ..repositories import assets as assets_repo
from ..repositories import projects as projects_repo
from ..repositories import timelines as timelines_repo
from ..services import analyzer, export, peaks
from ..services.ingest import ingest_upload
from ..services.queue import get_queue
from ..styles import presets
from ..styles.models import PresetSummary
from ..timelines.schema import Timeline, TimelineInfo, validate

router = APIRouter(prefix="/api/v1")

_FRAME_NAME = re.compile(r"^frame_\d{6}\.jpg$")


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.get("/styles")
def list_styles() -> list[PresetSummary]:
    """The editorial style preset gallery."""
    return presets.list_presets()


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


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, bool]:
    """Delete the project, its rows (FK cascade), and all artifact files."""
    _get_project(project_id)
    for asset in assets_repo.list_assets(project_id):
        shutil.rmtree(analyzer.asset_dir(asset.id), ignore_errors=True)
    projects_repo.delete_project(project_id)
    return {"deleted": True}


class RedraftRequest(BaseModel):
    """Re-run segment selection over cached analysis with a new style."""

    preset_id: str = "default"
    user_brief: str = Field(default="", max_length=2000)


@router.post("/projects/{project_id}/assets")
async def upload_asset(
    project_id: str,
    video: UploadFile = File(...),
    style_preset: str = Form("default"),
    user_brief: str = Form(""),
) -> Asset:
    _get_project(project_id)
    asset_id = await ingest_upload(
        video, project_id=project_id, style_preset=style_preset, user_brief=user_brief
    )
    return _get_asset(asset_id)


@router.post("/projects/{project_id}/redraft")
def redraft_project(project_id: str, body: RedraftRequest) -> dict[str, str | int]:
    """Re-draft every analyzed asset in the project with the given style.

    Each asset re-selects from its own cached analysis (no vision calls);
    drafts auto-assemble onto the project timeline.
    """
    _get_project(project_id)
    try:
        presets.load_preset(body.preset_id)
    except KeyError as exc:
        raise HTTPException(400, f"unknown style preset '{body.preset_id}'") from exc

    eligible = [a for a in assets_repo.list_assets(project_id) if a.frame_notes]
    if not eligible:
        raise HTTPException(409, "no analyzed assets to redraft — wait for the first pass")
    for asset in eligible:
        assets_repo.set_style(asset.id, body.preset_id, body.user_brief.strip())
        assets_repo.set_status(asset.id, "redrafting")
    get_queue().enqueue("redraft-project", project_id)
    return {"status": "redrafting", "assets": len(eligible)}


@router.post("/assets/{asset_id}/redraft")
def redraft_asset(asset_id: str, body: RedraftRequest) -> dict[str, str]:
    """Re-run selection with a new style over cached analysis (no vision calls)."""
    asset = _get_asset(asset_id)
    try:
        presets.load_preset(body.preset_id)
    except KeyError as exc:
        raise HTTPException(400, f"unknown style preset '{body.preset_id}'") from exc
    if not asset.frame_notes:
        raise HTTPException(409, "no cached analysis to redraft from — wait for the first pass")
    assets_repo.set_style(asset_id, body.preset_id, body.user_brief.strip())
    # Flip synchronously so clients observe the transition even before the
    # queue picks the task up (a crash here recovers via the redrafting map).
    assets_repo.set_status(asset_id, "redrafting")
    get_queue().enqueue("redraft", asset_id)
    return {"status": "redrafting"}


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


@router.get("/projects/{project_id}/export/{fmt}")
def export_timeline(project_id: str, fmt: str) -> Response:
    """Download the project timeline in an NLE-interchange format."""
    project = _get_project(project_id)
    try:
        _, _, document = analyzer.get_or_seed_timeline(project_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc

    slug = "".join(ch if ch.isalnum() else "-" for ch in project.name.lower()).strip("-")
    filename = slug or "timeline"
    if fmt == "srt":
        transcripts: dict[str, list[TranscriptLine]] = {}
        for track in document.tracks:
            for clip in track.clips:
                if clip.source.asset_id not in transcripts:
                    asset = assets_repo.get_asset(clip.source.asset_id)
                    transcripts[clip.source.asset_id] = asset.transcript if asset else []
        payload, media = export.export_srt(document, transcripts), "text/plain; charset=utf-8"
    elif fmt == "fcpxml":
        filenames: dict[str, str] = {}
        for track in document.tracks:
            for clip in track.clips:
                if clip.source.asset_id not in filenames:
                    asset = assets_repo.get_asset(clip.source.asset_id)
                    if asset is not None:
                        filenames[clip.source.asset_id] = asset.filename
        payload = export.export_fcpxml(document, filenames, name=project_id)
        media = "application/xml; charset=utf-8"
    elif fmt == "edl":
        fps = document.frame_rate or 30.0
        payload = export.export_edl(document, name=project_id, fps=fps)
        media = "text/plain; charset=utf-8"
    else:
        raise HTTPException(400, f"unknown export format '{fmt}' (srt, fcpxml, edl)")
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )


@router.get("/assets/{asset_id}/peaks")
def get_asset_peaks(asset_id: str) -> dict[str, Any]:
    """Waveform min/max buckets (~100 ms each), computed once and cached."""
    if assets_repo.get_asset(asset_id) is None:
        raise HTTPException(404, "asset not found")
    try:
        return peaks.get_peaks(asset_id)
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc


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
