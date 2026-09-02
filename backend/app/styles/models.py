"""The EditStyle contract (Plan 2).

A style is a *structured contract* plus prose: machine-checkable parameters
are enforced deterministically on the model's output (styles/enforcement.py),
while guidance and the user's free-form brief only shape the prompt. This
split is what makes "no slop drafts" possible — the model can ignore a
constraint and the draft still honors it.
"""

from typing import Literal

from pydantic import BaseModel, Field

CutOn = Literal["word", "sentence", "shot", "anywhere"]

DEFAULT_PRESET_ID = "default"


class EditStyle(BaseModel):
    preset_id: str = DEFAULT_PRESET_ID
    # Machine-checkable parameters (enforced post-selection):
    target_retention: float | None = Field(default=None, ge=0.0, le=1.0)
    target_segment_len_s: float | None = Field(default=None, gt=0)
    min_segment_s: float | None = Field(default=None, ge=0)
    max_segment_s: float | None = Field(default=None, gt=0)
    max_segment_count: int | None = Field(default=None, ge=1)
    cut_on: CutOn = "anywhere"
    # Prose guidance (prompt-only, never enforced):
    guidance: str = ""
    user_brief: str = ""

    def hard_constraints_text(self) -> str:
        """Human/model-readable rendering of the enforceable parameters."""
        rules: list[str] = []
        if self.min_segment_s is not None or self.max_segment_s is not None:
            lo = f"{self.min_segment_s:.0f}s" if self.min_segment_s is not None else "unbounded"
            hi = f"{self.max_segment_s:.0f}s" if self.max_segment_s is not None else "unbounded"
            rules.append(f"every keep-segment lasts between {lo} and {hi}")
        if self.max_segment_count is not None:
            rules.append(f"at most {self.max_segment_count} keep-segments")
        if self.target_retention is not None:
            rules.append(f"keep roughly {self.target_retention:.0%} of the video (±20%)")
        if self.cut_on != "anywhere":
            rules.append(f"cut on {self.cut_on} boundaries, never mid-{self.cut_on}")
        return "; ".join(rules) + "." if rules else "No hard pacing constraints."


class PresetSummary(BaseModel):
    """API-facing preset card."""

    preset_id: str
    name: str
    description: str
    pacing: str
