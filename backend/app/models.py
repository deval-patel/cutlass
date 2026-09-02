from typing import Literal, Optional
from pydantic import BaseModel, Field


class Segment(BaseModel):
    """A keep-range in the edit decision list."""
    start_s: float
    end_s: float
    reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FrameNote(BaseModel):
    timestamp_s: float
    description: str = ""
    label: Literal["core", "filler", "dead_air", "intro_outro", "repetition", "other"] = "other"


class VideoMeta(BaseModel):
    duration_s: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0


class JobStatus(BaseModel):
    id: str
    filename: str
    status: Literal["uploaded", "sampling", "analyzing", "ready", "rendering", "rendered", "failed"]
    error: Optional[str] = None
    meta: Optional[VideoMeta] = None
    segments: list[Segment] = []
    has_render: bool = False
