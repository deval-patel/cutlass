import json
import logging
from pathlib import Path

from .. import storage
from ..config import CHUNK_SIZE, SAMPLE_INTERVAL_S, TRANSCRIBE_CHUNK_S, TRANSCRIBE_ENABLED, UPLOADS_DIR
from ..models import Segment, TranscriptLine
from . import ffmpeg
from .providers.dry import get_provider

logger = logging.getLogger(__name__)


def job_dir(job_id: str) -> Path:
    return UPLOADS_DIR / job_id


def source_path(job_id: str) -> Path:
    return job_dir(job_id) / "source.mp4"


def render_path(job_id: str) -> Path:
    return job_dir(job_id) / "final_cut.mp4"


def frames_manifest(job_id: str) -> list[dict]:
    """[{t, file}] for every sampled frame, or [] if sampling hasn't run."""
    manifest = job_dir(job_id) / "frames.json"
    if not manifest.exists():
        return []
    return json.loads(manifest.read_text())


def _write_frames_manifest(job_id: str, frames: list[tuple[float, Path]]) -> None:
    payload = [{"t": round(ts, 2), "file": p.name} for ts, p in frames]
    (job_dir(job_id) / "frames.json").write_text(json.dumps(payload))


def transcribe_audio(job_id: str, provider, duration_s: float) -> list[TranscriptLine]:
    """Extract audio and transcribe it in time-chunks, offsetting each chunk's
    timestamps back to the original timeline."""
    lines: list[TranscriptLine] = []
    audio_dir = job_dir(job_id) / "audio"
    chunk_starts = []
    start = 0.0
    while start < duration_s:
        chunk_starts.append(start)
        start += TRANSCRIBE_CHUNK_S
    for i, chunk_start in enumerate(chunk_starts):
        storage.set_progress(job_id, f"transcribing audio {i + 1}/{len(chunk_starts)}")
        clip_len = min(TRANSCRIBE_CHUNK_S, duration_s - chunk_start)
        wav = ffmpeg.extract_audio(
            source_path(job_id), audio_dir / f"chunk_{i:03d}.wav",
            start_s=chunk_start, duration_s=clip_len,
        )
        for line in provider.transcribe(wav, clip_len):
            lines.append(TranscriptLine(
                start_s=chunk_start + line.start_s,
                end_s=chunk_start + line.end_s,
                text=line.text,
            ))
    return lines


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
        _write_frames_manifest(job_id, frames)
        storage.set_progress(job_id, f"extracted {len(frames)} frames")

        storage.set_status(job_id, "analyzing")

        transcript: list[TranscriptLine] = []
        if TRANSCRIBE_ENABLED:
            try:
                transcript = transcribe_audio(job_id, provider, meta.duration_s)
                storage.set_transcript(job_id, transcript)
            except Exception:  # noqa: BLE001 — audio is a bonus, not a gate
                logger.exception("transcription failed for job %s; continuing without audio", job_id)

        notes = []
        chunks = range(0, len(frames), CHUNK_SIZE)
        for i, start in enumerate(chunks):
            storage.set_progress(job_id, f"analyzing chunk {i + 1}/{len(chunks)}")
            chunk = frames[start : start + CHUNK_SIZE]
            notes.extend(provider.analyze_frames(chunk, meta.duration_s))
        storage.set_notes(job_id, notes)

        storage.set_progress(job_id, "selecting segments")
        segments = provider.select_segments(notes, meta.duration_s, transcript)
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
