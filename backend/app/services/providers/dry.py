from pathlib import Path

from ...models import FrameNote, Segment, TranscriptLine
from .base import MultimodalProvider


class DryRunProvider(MultimodalProvider):
    """Heuristic stub used when DRY_RUN=1 — no API calls, deterministic output."""

    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        return [
            FrameNote(timestamp_s=ts, description=f"(dry run) frame at {ts:.0f}s", label="core")
            for ts, _ in frames
        ]

    def transcribe(self, audio: Path, duration_s: float) -> list[TranscriptLine]:
        # One synthetic line per 30s so downstream code sees a realistic shape.
        lines = []
        t = 0.0
        while t < duration_s:
            end = min(t + 30.0, duration_s)
            lines.append(TranscriptLine(
                start_s=t, end_s=end, text=f"(dry run) speech from {t:.0f}s to {end:.0f}s",
            ))
            t = end
        return lines

    def select_segments(
        self,
        notes: list[FrameNote],
        total_duration_s: float,
        transcript: list[TranscriptLine] = [],
    ) -> list[Segment]:
        # Heuristic draft: drop the first 10% (intro) and last 10% (outro),
        # cut everything else into keep-segments with 1s gaps removed is
        # unnecessary — just keep one big middle segment.
        start = total_duration_s * 0.10
        end = total_duration_s * 0.90
        if end <= start:
            start, end = 0.0, total_duration_s
        return [Segment(start_s=start, end_s=end, reason="dry run: trimmed intro/outro", confidence=0.5)]


def get_provider() -> MultimodalProvider:
    from ... import config
    if config.DRY_RUN:
        return DryRunProvider()
    from .glm import GLMProvider
    return GLMProvider()
