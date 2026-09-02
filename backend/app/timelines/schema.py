"""Pydantic schema + invariants for timeline documents.

Timebase: seconds at the document boundary (floats); Plan 3's editor
quantizes to project frames internally. Every clip's record duration
equals its source duration — speed effects come later as an explicit
modifier, so no hidden time math exists yet.
"""

import uuid
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, Field

from ..models import Segment

TrackKind = Literal["video", "audio"]

SCHEMA_VERSION = 1


class ClipSource(BaseModel):
    """Which part of which asset the clip plays."""

    asset_id: str
    in_s: float
    out_s: float


class Clip(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    source: ClipSource
    record_start_s: float = 0.0
    # Provenance from the AI draft (Plan 2 grows this into style metadata).
    reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    enabled: bool = True


class Track(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: TrackKind = "video"
    name: str  # "V1", "A1", ...
    clips: list[Clip] = []


class DraftMeta(BaseModel):
    """Provenance of an AI-generated draft (Plan 2): which prompt and style
    produced it, plus measured stats — every draft's 'why' is answerable."""

    prompt_version: str
    style_preset: str = "default"
    user_brief: str = ""
    retention: float | None = None
    avg_segment_s: float | None = None
    generated_at: str | None = None


class Timeline(BaseModel):
    schema_version: int = SCHEMA_VERSION
    name: str = "main"
    frame_rate: float | None = None
    tracks: list[Track] = []
    meta: DraftMeta | None = None


class TimelineInfo(BaseModel):
    """API envelope: a stored timeline with identity and version."""

    id: str
    project_id: str
    name: str
    version: int
    document: Timeline
    updated_at: str | None = None


def duration_s(timeline: Timeline) -> float:
    """Total record duration across all tracks (max record end)."""
    end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.enabled:
                end = max(end, clip.record_start_s + (clip.source.out_s - clip.source.in_s))
    return end


def validate(timeline: Timeline) -> None:
    """Enforce document invariants. Raises ValueError with a clear message."""
    track_names: set[str] = set()
    for track in timeline.tracks:
        if track.name in track_names:
            raise ValueError(f"duplicate track name {track.name!r}")
        track_names.add(track.name)

    if timeline.frame_rate is not None and timeline.frame_rate <= 0:
        raise ValueError("frame_rate must be positive")

    seen_clip_ids: set[str] = set()
    for track in timeline.tracks:
        ordered: list[tuple[float, float]] = []
        for clip in track.clips:
            if clip.id in seen_clip_ids:
                raise ValueError(f"duplicate clip id {clip.id!r}")
            seen_clip_ids.add(clip.id)
            if clip.source.out_s <= clip.source.in_s:
                raise ValueError(f"clip {clip.id!r}: source range is empty")
            if not clip.enabled:
                continue
            ordered.append(
                (clip.record_start_s, clip.record_start_s + (clip.source.out_s - clip.source.in_s))
            )
        ordered.sort()
        for (_, end_a), (start_b, _) in pairwise(ordered):
            if start_b < end_a - 1e-9:
                raise ValueError(
                    f"track {track.name!r}: clips overlap at record time {start_b:.3f}s"
                )


def from_segments(
    segments: list[Segment], asset_id: str, frame_rate: float | None = None
) -> Timeline:
    """Represent a flat keep-segment EDL as a single-track timeline.

    Record times are contiguous (gaps removed) — exactly what the current
    renderer produces, so the legacy view and the timeline view of a draft
    agree.
    """
    clips: list[Clip] = []
    cursor = 0.0
    for seg in segments:
        clips.append(
            Clip(
                source=ClipSource(asset_id=asset_id, in_s=seg.start_s, out_s=seg.end_s),
                record_start_s=cursor,
                reason=seg.reason,
                confidence=seg.confidence,
            )
        )
        cursor += seg.end_s - seg.start_s
    return Timeline(
        frame_rate=frame_rate,
        tracks=[Track(name="V1", kind="video", clips=clips)],
    )


def to_segments(timeline: Timeline) -> list[Segment]:
    """Flatten the first video track back to a keep-segment EDL (legacy render).

    Clips are taken in record order and mapped to their source ranges.
    """
    track = next((t for t in timeline.tracks if t.kind == "video" and t.clips), None)
    if track is None:
        return []
    segments = []
    for clip in sorted((c for c in track.clips if c.enabled), key=lambda c: c.record_start_s):
        segments.append(
            Segment(
                start_s=clip.source.in_s,
                end_s=clip.source.out_s,
                reason=clip.reason,
                confidence=clip.confidence,
            )
        )
    return segments
