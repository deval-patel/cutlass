"""Analysis pipeline and rendering, asset-centric since Plan 1.

Paths are keyed by asset id under uploads/; rendering consumes the
project's timeline document (seeded from the draft EDL when missing).
"""

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import config
from ..models import FrameNote, Segment, TranscriptLine
from ..prompts.builder import CURRENT_VERSION
from ..repositories import assets as assets_repo
from ..repositories import timelines as timelines_repo
from ..styles import enforcement as enf
from ..styles import metrics
from ..styles.models import EditStyle
from ..styles.presets import resolve_style
from ..timelines import schema as timeline_schema
from . import ffmpeg
from .providers.base import MultimodalProvider
from .providers.dry import get_provider

logger = logging.getLogger(__name__)


def asset_dir(asset_id: str) -> Path:
    return config.UPLOADS_DIR / asset_id


def source_path(asset_id: str) -> Path:
    return asset_dir(asset_id) / "source.mp4"


def render_path(asset_id: str) -> Path:
    return asset_dir(asset_id) / "final_cut.mp4"


def frames_manifest(asset_id: str) -> list[dict[str, Any]]:
    """[{t, file}] for every sampled frame, or [] if sampling hasn't run."""
    manifest = asset_dir(asset_id) / "frames.json"
    if not manifest.exists():
        return []
    parsed: list[dict[str, Any]] = json.loads(manifest.read_text())
    return parsed


def _write_frames_manifest(asset_id: str, frames: list[tuple[float, Path]]) -> None:
    payload = [{"t": round(ts, 2), "file": p.name} for ts, p in frames]
    (asset_dir(asset_id) / "frames.json").write_text(json.dumps(payload))


def sync_timeline_from_draft(asset_id: str) -> None:
    """Merge the asset's draft EDL into the project timeline (multi-asset aware).

    Called when the pipeline produces a draft, when a re-draft lands, and
    when the legacy segment editor saves edits. Semantics: an asset whose
    clips already sit on the timeline has them REPLACED and moved to the
    end (predictable, never overlapping); a new asset's clips append at
    the end. Stamps DraftMeta so every draft's provenance is answerable.
    """
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        raise RuntimeError(f"unknown asset {asset_id}")
    fps = asset.meta.fps if asset.meta else None
    duration = asset.meta.duration_s if asset.meta else 0.0

    fresh = timeline_schema.from_segments(asset.segments, asset_id=asset_id, frame_rate=fps)
    fresh_clips = fresh.tracks[0].clips

    stored = timelines_repo.get_timeline(asset.project_id)
    if stored is None:
        document = fresh
    else:
        _, _, document = stored
        track_idx = next((i for i, t in enumerate(document.tracks) if t.kind == "video"), None)
        if track_idx is None:
            document.tracks.append(fresh.tracks[0].model_copy())
        else:
            track = document.tracks[track_idx]
            others = [c for c in track.clips if c.source.asset_id != asset_id]
            offset = max(
                (c.record_start_s + (c.source.out_s - c.source.in_s) for c in others),
                default=0.0,
            )
            moved = [
                c.model_copy(update={"record_start_s": round(offset + c.record_start_s, 3)})
                for c in fresh_clips
            ]
            document.tracks[track_idx] = track.model_copy(update={"clips": others + moved})

    document.meta = timeline_schema.DraftMeta(
        prompt_version=CURRENT_VERSION,
        style_preset=asset.style_preset,
        user_brief=asset.user_brief,
        retention=round(metrics.retention(asset.segments, duration), 4) if duration else None,
        avg_segment_s=round(metrics.avg_segment_s(asset.segments), 3) if asset.segments else None,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    timelines_repo.save_timeline(asset.project_id, document, label=f"draft: {asset.style_preset}")


def _select_draft(
    provider: MultimodalProvider,
    notes: list[FrameNote],
    transcript: list[TranscriptLine] | None,
    duration_s: float,
    style: EditStyle,
) -> list[Segment]:
    """Model selection + deterministic enforcement + one retention re-prompt.

    The enforcement pass guarantees the style's hard constraints regardless
    of model behavior; the retention feedback loop nudges the *model* toward
    the soft target and keeps whichever attempt lands closer.
    """
    segments = enf.enforce_segments(
        provider.select_segments(notes, duration_s, transcript, style=style),
        style,
        duration_s,
        transcript,
    )
    feedback = enf.retention_feedback(style, metrics.retention(segments, duration_s))
    if feedback:
        logger.info("retention feedback re-prompt: %s", feedback)
        retry = enf.enforce_segments(
            provider.select_segments(notes, duration_s, transcript, style=style, feedback=feedback),
            style,
            duration_s,
            transcript,
        )
        base_delta = metrics.retention_delta(segments, style, duration_s)
        retry_delta = metrics.retention_delta(retry, style, duration_s)
        if retry and (retry_delta is not None and base_delta is not None):
            if abs(retry_delta) < abs(base_delta):
                segments = retry
        elif retry:
            segments = retry
    return segments


def get_or_seed_timeline(project_id: str) -> tuple[str, int, timeline_schema.Timeline]:
    """Current timeline, seeding from the project's single-asset draft if absent.

    Migrated pre-Plan-1 projects have no timeline row until first read.
    """
    stored = timelines_repo.get_timeline(project_id)
    if stored is not None:
        return stored
    assets = assets_repo.list_assets(project_id)
    if len(assets) != 1:
        raise RuntimeError(
            f"project {project_id} has no timeline and {len(assets)} assets; "
            "cannot seed from a draft"
        )
    asset = assets[0]
    fps = asset.meta.fps if asset.meta else None
    document = timeline_schema.from_segments(asset.segments, asset_id=asset.id, frame_rate=fps)
    timeline_id, version = timelines_repo.save_timeline(
        project_id, document, label="seeded from draft"
    )
    return timeline_id, version, document


def transcribe_audio(
    asset_id: str, provider: MultimodalProvider, duration_s: float
) -> list[TranscriptLine]:
    """Extract audio and transcribe it in time-chunks, offsetting each chunk's
    timestamps back to the original timeline."""
    lines: list[TranscriptLine] = []
    audio_dir = asset_dir(asset_id) / "audio"
    chunk_starts = []
    start = 0.0
    while start < duration_s:
        chunk_starts.append(start)
        start += config.TRANSCRIBE_CHUNK_S
    for i, chunk_start in enumerate(chunk_starts):
        assets_repo.set_progress(asset_id, f"transcribing audio {i + 1}/{len(chunk_starts)}")
        clip_len = min(config.TRANSCRIBE_CHUNK_S, duration_s - chunk_start)
        wav = ffmpeg.extract_audio(
            source_path(asset_id),
            audio_dir / f"chunk_{i:03d}.wav",
            start_s=chunk_start,
            duration_s=clip_len,
        )
        for line in provider.transcribe(wav, clip_len):
            lines.append(
                TranscriptLine(
                    start_s=chunk_start + line.start_s,
                    end_s=chunk_start + line.end_s,
                    text=line.text,
                )
            )
    return lines


def run_pipeline(asset_id: str) -> None:
    """Full analysis: probe → sample → chunked analysis → global pass → EDL → timeline."""
    try:
        asset = assets_repo.get_asset(asset_id)
        if asset is None:
            logger.warning("asset %s vanished before analysis; skipping", asset_id)
            return
        style = resolve_style(asset.style_preset, asset.user_brief)
        provider = get_provider()
        video = source_path(asset_id)

        assets_repo.set_progress(asset_id, "probing video")
        meta = ffmpeg.probe(video)
        assets_repo.set_meta(asset_id, meta)

        assets_repo.set_status(asset_id, "sampling")
        interval = config.SAMPLE_INTERVAL_S
        # For short videos sample at least every 1s so we get enough signal.
        if 0 < meta.duration_s < 60:
            interval = min(interval, 1.0)
        frames = ffmpeg.extract_frames(video, asset_dir(asset_id) / "frames", interval)
        if not frames:
            raise RuntimeError("no frames extracted; is the video valid?")
        _write_frames_manifest(asset_id, frames)
        assets_repo.set_progress(asset_id, f"extracted {len(frames)} frames")

        assets_repo.set_status(asset_id, "analyzing")

        transcript: list[TranscriptLine] = []
        if config.TRANSCRIBE_ENABLED:
            try:
                transcript = transcribe_audio(asset_id, provider, meta.duration_s)
                assets_repo.set_transcript(asset_id, transcript)
            except Exception:
                logger.exception(
                    "transcription failed for asset %s; continuing without audio", asset_id
                )

        notes: list[FrameNote] = []
        chunks = range(0, len(frames), config.CHUNK_SIZE)
        for i, start in enumerate(chunks):
            assets_repo.set_progress(asset_id, f"analyzing chunk {i + 1}/{len(chunks)}")
            chunk = frames[start : start + config.CHUNK_SIZE]
            notes.extend(provider.analyze_frames(chunk, meta.duration_s))
        assets_repo.set_notes(asset_id, notes)

        assets_repo.set_progress(asset_id, "selecting segments")
        segments = _select_draft(provider, notes, transcript, meta.duration_s, style)
        if not segments:
            raise RuntimeError("model returned no keep-segments")
        assets_repo.set_segments(asset_id, segments)
        sync_timeline_from_draft(asset_id)
        # Transcription chunks were scratch space; the transcript is stored.
        shutil.rmtree(asset_dir(asset_id) / "audio", ignore_errors=True)
        assets_repo.set_progress(asset_id, None)
        assets_repo.set_status(asset_id, "ready")
    except Exception as exc:
        logger.exception("pipeline failed for asset %s", asset_id)
        assets_repo.set_status(asset_id, "failed", error=str(exc))


def _redraft_one(asset_id: str) -> None:
    """Re-select one asset's draft from cached analysis. Raises on failure."""
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        raise RuntimeError(f"unknown asset {asset_id}")
    if not asset.frame_notes:
        raise RuntimeError("no cached frame analysis to redraft from")
    if asset.meta is None:
        raise RuntimeError("asset metadata missing; cannot redraft")
    assets_repo.set_progress(asset_id, "re-selecting segments")

    style = resolve_style(asset.style_preset, asset.user_brief)
    provider = get_provider()
    segments = _select_draft(
        provider, asset.frame_notes, asset.transcript or None, asset.meta.duration_s, style
    )
    if not segments:
        raise RuntimeError("model returned no keep-segments")
    assets_repo.set_segments(asset_id, segments)
    sync_timeline_from_draft(asset_id)
    assets_repo.set_progress(asset_id, None)
    assets_repo.set_status(asset_id, "ready")


def run_redraft(asset_id: str) -> None:
    """Re-run *only* segment selection over cached analysis with a new style.

    No vision calls, no transcription: frame notes and transcript are
    already stored, so a re-draft is one (or two, with retention feedback)
    text-model calls plus deterministic enforcement — cheap enough to
    A/B styles.
    """
    try:
        if assets_repo.get_asset(asset_id) is None:
            logger.warning("asset %s vanished before redraft; skipping", asset_id)
            return
        _redraft_one(asset_id)
    except Exception as exc:
        logger.exception("redraft failed for asset %s", asset_id)
        assets_repo.set_status(asset_id, "failed", error=str(exc))


def run_project_redraft(project_id: str) -> None:
    """Re-draft every analyzed asset in the project with its stored style.

    Each asset's selection is independent (its own cached notes), and each
    draft auto-assembles onto the project timeline via sync — one call
    restyles the whole trip. A failing asset is marked failed; siblings
    continue.
    """
    assets = [a for a in assets_repo.list_assets(project_id) if a.frame_notes]
    logger.info("project redraft for %s: %d assets", project_id, len(assets))
    for asset in assets:
        try:
            _redraft_one(asset.id)
        except Exception as exc:
            logger.exception("project redraft failed for asset %s", asset.id)
            assets_repo.set_status(asset.id, "failed", error=str(exc))


def run_render(asset_id: str) -> None:
    """Render the asset's project timeline into final_cut.mp4.

    Multi-asset timelines render via per-clip trims concatenated in record
    order (one ffmpeg input per unique asset). The artifact lands beside
    the asset that triggered the render.
    """
    try:
        asset = assets_repo.get_asset(asset_id)
        if asset is None:
            logger.warning("asset %s vanished before render; skipping", asset_id)
            return
        assets_repo.set_status(asset_id, "rendering")

        _, _, document = get_or_seed_timeline(asset.project_id)
        track = next((t for t in document.tracks if t.kind == "video"), None)
        clips = (
            [c for c in sorted(track.clips, key=lambda c: c.record_start_s) if c.enabled]
            if track
            else []
        )
        if not clips:
            raise RuntimeError("timeline has no enabled clips to render")
        specs = [
            (
                source_path(clip.source.asset_id),
                clip.source.in_s,
                clip.source.out_s,
                clip.transition_out.duration_s if clip.transition_out else None,
            )
            for clip in clips
        ]
        ffmpeg.render_timeline(specs, render_path(asset_id))
        assets_repo.set_status(asset_id, "rendered")
    except Exception as exc:
        logger.exception("render failed for asset %s", asset_id)
        assets_repo.set_status(asset_id, "failed", error=str(exc))
