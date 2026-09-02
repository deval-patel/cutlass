from typing import Literal

from pydantic import BaseModel, Field

JobStatusValue = Literal[
    "uploaded", "sampling", "analyzing", "ready", "rendering", "rendered", "failed"
]


class Segment(BaseModel):
    """A keep-range in the edit decision list."""

    start_s: float
    end_s: float
    reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


FrameNoteLabel = Literal["core", "filler", "dead_air", "intro_outro", "repetition", "other"]


class FrameNote(BaseModel):
    timestamp_s: float
    description: str = ""
    label: FrameNoteLabel = "other"


class TranscriptLine(BaseModel):
    start_s: float
    end_s: float
    text: str


class VideoMeta(BaseModel):
    duration_s: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0


class JobStatus(BaseModel):
    id: str
    filename: str
    status: JobStatusValue
    error: str | None = None
    meta: VideoMeta | None = None
    segments: list[Segment] = []
    has_render: bool = False
    created_at: str | None = None
    progress: str | None = None
    frame_notes: list[FrameNote] = []
    transcript: list[TranscriptLine] = []
