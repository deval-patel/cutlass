from abc import ABC, abstractmethod
from pathlib import Path

from ...models import FrameNote, Segment


class MultimodalProvider(ABC):
    """Pluggable interface for AI analysis backends."""

    @abstractmethod
    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        """Describe/label a batch of (timestamp, image) frames."""

    @abstractmethod
    def select_segments(self, notes: list[FrameNote], total_duration_s: float) -> list[Segment]:
        """Given per-frame notes over the whole video, pick keep-segments."""
