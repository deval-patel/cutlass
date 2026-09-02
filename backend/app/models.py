from typing import Literal

from pydantic import BaseModel, Field

JobStatusValue = Literal[
    "uploaded",
    "sampling",
    "analyzing",
    "redrafting",
    "ready",
    "rendering",
    "rendered",
    "failed",
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


class Asset(BaseModel):
    """An ingested source file plus its analysis.

    Lives in a project; the pre-Plan-1 'job' became exactly this (ids were
    preserved by the cutover migration, so legacy /api/jobs/{id} URLs work).
    """

    id: str
    project_id: str
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
    # Editorial style (Plan 2): set at upload or by a re-draft request.
    style_preset: str = "default"
    user_brief: str = ""


class Project(BaseModel):
    id: str
    name: str
    user_id: str | None = None
    created_at: str | None = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: str | None = None
    assets: int = 0
    duration_s: float | None = None
    timeline_id: str | None = None
