"""Upload ingestion: validation, streaming to disk, project/asset creation.

Shared by the legacy /api/upload shim and the /api/v1 project asset
upload, so validation rules exist exactly once.
"""

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .. import config
from ..repositories import assets as assets_repo
from ..repositories import projects as projects_repo
from . import analyzer, ffmpeg
from .queue import get_queue

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


async def ingest_upload(
    video: UploadFile, project_id: str | None = None, project_name: str | None = None
) -> str:
    """Validate and store an upload, register it as an asset, queue analysis.

    Without a project_id, a fresh project is created for the upload (the
    legacy one-video-per-project flow). Returns the asset id.
    """
    ext = Path(video.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(400, f"unsupported file type '{ext or '(none)'}' — allowed: {allowed}")

    asset_id = uuid.uuid4().hex[:12]
    directory = analyzer.asset_dir(asset_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = analyzer.source_path(asset_id)

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
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(413, f"file exceeds {config.MAX_UPLOAD_GB}GB limit")

    # Fail fast on files that aren't actually readable video.
    try:
        ffmpeg.probe(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(400, "file could not be read as a video (ffprobe failed)") from exc

    if project_id is None:
        project_id = uuid.uuid4().hex[:12]
        projects_repo.create_project(project_id, project_name or video.filename or "video.mp4")
    assets_repo.create_asset(asset_id, project_id, video.filename or "video.mp4")
    get_queue().enqueue("analyze", asset_id)
    return asset_id
