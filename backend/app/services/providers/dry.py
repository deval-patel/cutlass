from pathlib import Path

from ...models import FrameNote, Segment
from .base import MultimodalProvider


class DryRunProvider(MultimodalProvider):
    """Heuristic stub used when DRY_RUN=1 — no API calls, deterministic output."""

    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        interval = frames[1][0] - frames[0][0] if len(frames) > 1 else 1.0
        return [
            FrameNote(timestamp_s=ts, description=f"(dry run) frame at {ts:.0f}s", label="core")
            for ts, _ in frames
        ]

    def select_segments(self, notes: list[FrameNote], total_duration_s: float) -> list[Segment]:
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
