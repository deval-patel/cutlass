from abc import ABC, abstractmethod
from pathlib import Path

from ...models import FrameNote, Segment, TranscriptLine


class MultimodalProvider(ABC):
    """Pluggable interface for AI analysis backends."""

    @abstractmethod
    def analyze_frames(
        self, frames: list[tuple[float, Path]], total_duration_s: float
    ) -> list[FrameNote]:
        """Describe/label a batch of (timestamp, image) frames."""

    @abstractmethod
    def select_segments(
        self,
        notes: list[FrameNote],
        total_duration_s: float,
        transcript: list[TranscriptLine] = [],
    ) -> list[Segment]:
        """Given per-frame notes (and optionally a transcript) over the whole
        video, pick keep-segments."""

    def transcribe(self, audio: Path, duration_s: float) -> list[TranscriptLine]:
        """Transcribe an audio file; return timestamped lines. Optional."""
        return []
