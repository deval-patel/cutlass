"""Selection-quality metrics (Plan 2): the vocabulary of the eval harness.

These functions compare two drafts (or a draft against its style targets)
and are the shared language of CI regression checks and the golden set.
"""

from collections.abc import Sequence

from ..models import Segment
from .models import EditStyle


def total_duration(segments: Sequence[Segment]) -> float:
    return sum(s.end_s - s.start_s for s in segments)


def retention(segments: Sequence[Segment], original_duration_s: float) -> float:
    """Kept time divided by source duration."""
    if original_duration_s <= 0:
        return 0.0
    return total_duration(segments) / original_duration_s


def avg_segment_s(segments: Sequence[Segment]) -> float:
    """Mean keep-segment length (the ASL proxy)."""
    return total_duration(segments) / len(segments) if segments else 0.0


def selection_iou(a: Sequence[Segment], b: Sequence[Segment]) -> float:
    """Intersection-over-union of two keep-segment selections.

    1.0 = identical timelines, 0.0 = disjoint. Symmetric; computed on
    total overlap, so overlapping pairs across boundaries are fine.
    """
    union = total_duration(a) + total_duration(b)
    if union <= 0:
        return 0.0
    intersection = 0.0
    for seg_a in a:
        for seg_b in b:
            overlap = min(seg_a.end_s, seg_b.end_s) - max(seg_a.start_s, seg_b.start_s)
            if overlap > 0:
                intersection += overlap
    return intersection / (union - intersection)


def pacing_deviation(segments: Sequence[Segment], style: EditStyle) -> float | None:
    """|avg segment length - target| / target; None without a length target."""
    if style.target_segment_len_s is None or not segments:
        return None
    target = style.target_segment_len_s
    return abs(avg_segment_s(segments) - target) / target


def retention_delta(
    segments: Sequence[Segment], style: EditStyle, original_duration_s: float
) -> float | None:
    """Measured retention minus the style's target; None without a target."""
    if style.target_retention is None:
        return None
    return retention(segments, original_duration_s) - style.target_retention
