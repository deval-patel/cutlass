import logging
from pathlib import Path

from .. import storage
from ..config import CHUNK_SIZE, SAMPLE_INTERVAL_S, UPLOADS_DIR
from ..models import Segment
from . import ffmpeg
from .providers.dry import get_provider

logger = logging.getLogger(__name__)


def job_dir(job_id: str) -> Path:
    return UPLOADS_DIR / job_id


def source_path(job_id: str) -> Path:
    return job_dir(job_id) / "source.mp4"


def render_path(job_id: str) -> Path:
    return job_dir(job_id) / "final_cut.mp4"


def run_pipeline(job_id: str) -> None:
    """Full analysis pipeline: probe → sample → chunked analysis → global pass → EDL."""
    try:
        provider = get_provider()
        video = source_path(job_id)

        storage.set_progress(job_id, "probing video")
        meta = ffmpeg.probe(video)
        storage.set_meta(job_id, meta)

        storage.set_status(job_id, "sampling")
        interval = SAMPLE_INTERVAL_S
        # For short videos sample at least every 1s so we get enough signal.
        if 0 < meta.duration_s < 60:
            interval = min(interval, 1.0)
        frames = ffmpeg.extract_frames(video, job_dir(job_id) / "frames", interval)
        if not frames:
            raise RuntimeError("no frames extracted; is the video valid?")
        storage.set_progress(job_id, f"extracted {len(frames)} frames")

        storage.set_status(job_id, "analyzing")
        notes = []
        chunks = range(0, len(frames), CHUNK_SIZE)
        for i, start in enumerate(chunks):
            storage.set_progress(job_id, f"analyzing chunk {i + 1}/{len(chunks)}")
            chunk = frames[start : start + CHUNK_SIZE]
            notes.extend(provider.analyze_frames(chunk, meta.duration_s))
        storage.set_notes(job_id, notes)

        storage.set_progress(job_id, "selecting segments")
        segments = provider.select_segments(notes, meta.duration_s)
        if not segments:
            raise RuntimeError("model returned no keep-segments")
        storage.set_segments(job_id, segments)
        storage.set_progress(job_id, None)
        storage.set_status(job_id, "ready")
    except Exception as exc:  # noqa: BLE001 — job isolation
        logger.exception("pipeline failed for job %s", job_id)
        storage.set_status(job_id, "failed", error=str(exc))


def run_render(job_id: str) -> None:
    try:
        job = storage.get_job(job_id)
        if job is None or not job.segments:
            raise RuntimeError("no segments to render")
        storage.set_status(job_id, "rendering")
        ranges = [(s.start_s, s.end_s) for s in job.segments]
        ffmpeg.render_cut(source_path(job_id), ranges, render_path(job_id))
        storage.set_status(job_id, "rendered")
    except Exception as exc:  # noqa: BLE001
        logger.exception("render failed for job %s", job_id)
        storage.set_status(job_id, "failed", error=str(exc))
