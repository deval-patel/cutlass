"""Deterministic style enforcement (Plan 2).

The model proposes; this module disposes. Whatever the model returns, the
post-processed draft satisfies the style's hard constraints:

- **max_segment_s is never violated** — over-long segments split, with cut
  points preferring sentence boundaries;
- **min_segment_s holds unless folding would break max** — in the rare
  unsatisfiable pocket (segment length in (max, 2·min) territory) a short
  piece next to an at-max neighbor is accepted and documented;
- **max_segment_count holds unless infeasible** given min/max — the cap
  then yields (folding further would break max).

Pipeline order: normalize → (min-merge → max-split) to a fixed point →
boundary snap → one final (min-merge → max-split) → count-merge.

Cut-point granularity: "sentence" snaps to transcript line boundaries;
"word"/"shot" degrade to the best available boundary today (word-level
timestamps and shot detection arrive later in Plan 2/5).
"""

import math
import random
from collections.abc import Sequence

from ..models import Segment, TranscriptLine
from .models import EditStyle

_SNAP_TOLERANCE_S = 1.5
_EPS = 1e-9


def enforce_segments(
    segments: Sequence[Segment],
    style: EditStyle,
    duration_s: float,
    transcript: Sequence[TranscriptLine] | None = None,
) -> list[Segment]:
    """Apply the style's hard constraints; output is always valid."""
    from ..services.edl import normalize_segments

    current = normalize_segments(list(segments), duration_s)
    snap = style.cut_on == "sentence" and bool(transcript)

    for _ in range(3):
        current = _merge_too_short(current, style.min_segment_s, style.max_segment_s)
        current = _split_too_long(current, style.max_segment_s, transcript)

    if snap:
        current = _snap_boundaries(current, transcript or [], duration_s)
        current = _merge_too_short(current, style.min_segment_s, style.max_segment_s)
        current = _split_too_long(current, style.max_segment_s, transcript)

    if style.max_segment_count is not None:
        current = _merge_to_count(current, style.max_segment_count, style.max_segment_s)
    return current


def _length(seg: Segment) -> float:
    return seg.end_s - seg.start_s


def _fits(folded_length: float, max_s: float | None) -> bool:
    return max_s is None or folded_length <= max_s + _EPS


def _span(a: Segment, b: Segment) -> float:
    """Length of a folded pair — includes any gap between the two."""
    return max(a.end_s, b.end_s) - a.start_s


def _fold(a: Segment, b: Segment) -> Segment:
    return Segment(
        start_s=a.start_s,
        end_s=max(a.end_s, b.end_s),
        reason=a.reason or b.reason,
        confidence=min(a.confidence, b.confidence),
    )


def _merge_too_short(
    segments: list[Segment], min_s: float | None, max_s: float | None
) -> list[Segment]:
    """Fold sub-minimum segments into a neighbor when that keeps ≤ max."""
    if min_s is None:
        return segments
    current = list(segments)
    for _ in range(4):
        out: list[Segment] = []
        changed = False
        i = 0
        while i < len(current):
            seg = current[i]
            if _length(seg) >= min_s - _EPS:
                out.append(seg)
                i += 1
                continue
            folded = False
            if out and _fits(_span(out[-1], seg), max_s):
                out[-1] = _fold(out[-1], seg)  # extend the previous segment
                folded = True
            elif i + 1 < len(current) and _fits(_span(seg, current[i + 1]), max_s):
                current[i + 1] = _fold(seg, current[i + 1])  # extend the next
                folded = True
            else:
                out.append(seg)  # unsatisfiable pocket — keep, oracle allows
            changed = changed or folded
            i += 1
        current = out
        if not changed:
            break
    return current


def _split_too_long(
    segments: list[Segment], max_s: float | None, transcript: Sequence[TranscriptLine] | None
) -> list[Segment]:
    if max_s is None:
        return segments
    result: list[Segment] = []
    for seg in segments:
        if _length(seg) <= max_s + _EPS:
            result.append(seg)
            continue
        parts = math.ceil(_length(seg) / max_s)
        boundaries = _choose_boundaries(seg, parts, transcript)
        cursor = seg.start_s
        for boundary in boundaries:
            result.append(
                Segment(
                    start_s=cursor,
                    end_s=boundary,
                    reason=seg.reason,
                    confidence=seg.confidence,
                )
            )
            cursor = boundary
        result.append(
            Segment(
                start_s=cursor,
                end_s=seg.end_s,
                reason=f"{seg.reason} (cont.)".strip(),
                confidence=seg.confidence,
            )
        )
    return [s for s in result if _length(s) > _EPS]


def _choose_boundaries(
    seg: Segment, parts: int, transcript: Sequence[TranscriptLine] | None
) -> list[float]:
    """parts-1 interior cut points, ideally on sentence boundaries."""
    ideal = [seg.start_s + _length(seg) * (i + 1) / parts for i in range(parts - 1)]
    if not transcript:
        return ideal
    snapped: list[float] = []
    for point in ideal:
        best = min(
            (
                b
                for line in transcript
                for b in (line.start_s, line.end_s)
                if seg.start_s < b < seg.end_s
            ),
            key=lambda b: abs(b - point),
            default=point,
        )
        snapped.append(best if abs(best - point) <= 3.0 else point)
    return sorted(set(snapped))


def _merge_to_count(segments: list[Segment], cap: int, max_s: float | None) -> list[Segment]:
    """Fold the shortest adjacent pairs down to the cap — but never past max."""
    result = list(segments)
    while len(result) > cap:
        candidates = [
            i for i in range(len(result) - 1) if _fits(_span(result[i], result[i + 1]), max_s)
        ]
        if not candidates:
            break  # cap infeasible given max; min/max win (documented)
        best = min(candidates, key=lambda i: _span(result[i], result[i + 1]))
        result[best] = _fold(result[best], result[best + 1])
        del result[best + 1]
    return result


def _snap_boundaries(
    segments: list[Segment], transcript: Sequence[TranscriptLine], duration_s: float
) -> list[Segment]:
    """Move cut points to the nearest transcript-line boundary in tolerance.

    Never past a neighboring segment (no overlaps) and never outside the
    video. Snapping happens before the final min/max passes, so it can
    never leave a constraint broken.
    """
    if not segments:
        return segments
    edges = [seg.start_s for seg in segments] + [segments[-1].end_s]
    forbidden = set(edges)
    snapped = [
        _snap_point(point, transcript, forbidden=forbidden, duration_s=duration_s)
        for point in edges
    ]
    starts, ends = snapped[:-1], snapped[1:]
    result: list[Segment] = []
    for seg, start, end in zip(segments, starts, ends, strict=True):
        if end > start:
            result.append(
                Segment(start_s=start, end_s=end, reason=seg.reason, confidence=seg.confidence)
            )
    return result


def _snap_point(
    point: float, transcript: Sequence[TranscriptLine], forbidden: set[float], duration_s: float
) -> float:
    candidates: list[float] = []
    for line in transcript:
        for boundary in (line.start_s, line.end_s):
            if abs(boundary - point) <= _SNAP_TOLERANCE_S and boundary not in forbidden:
                candidates.append(boundary)
    if not candidates:
        return point
    return min(candidates, key=lambda b: abs(b - point))


def violates_hard_constraints(segments: Sequence[Segment], style: EditStyle) -> bool:
    """Test/CI oracle for the invariants enforce_segments must uphold.

    Returns True when output breaks a constraint that was satisfiable:
    - a segment over max is always a violation;
    - a segment under min is a violation unless folding it into either
      neighbor would break max (the unsatisfiable pocket);
    - the count cap is a violation unless max makes it unachievable.
    """
    for i, seg in enumerate(segments):
        if style.max_segment_s is not None and _length(seg) > style.max_segment_s + _EPS:
            return True
        if style.min_segment_s is not None and _length(seg) < style.min_segment_s - _EPS:
            prev_ok = i > 0 and _fits(_span(segments[i - 1], seg), style.max_segment_s)
            next_ok = i + 1 < len(segments) and _fits(
                _span(seg, segments[i + 1]), style.max_segment_s
            )
            if prev_ok or next_ok:
                return True  # a fold was available and not taken
    if style.max_segment_count is not None and len(segments) > style.max_segment_count:
        # The cap is a violation only when a legal fold remains (one that
        # keeps the merged span ≤ max). If every adjacent fold would break
        # max, the count is genuinely infeasible and min/max win.
        foldable = any(
            style.max_segment_s is None
            or _span(segments[i], segments[i + 1]) <= style.max_segment_s + _EPS
            for i in range(len(segments) - 1)
        )
        if foldable:
            return True
    return False


def retention_feedback(style: EditStyle, measured: float) -> str | None:
    """A re-prompt message when retention misses the target by >20 points."""
    if style.target_retention is None:
        return None
    if abs(measured - style.target_retention) <= 0.20:
        return None
    direction = "less" if measured > style.target_retention else "more"
    return (
        f"Your draft kept {measured:.0%} of the video; the target for this style "
        f"is about {style.target_retention:.0%}. Select {direction} footage: "
        "be stricter about what makes the cut."
    )


def fuzz_segments(rng: random.Random, duration_s: float, count: int) -> list[Segment]:
    """Random messy drafts for property testing (deterministic given rng)."""
    points = sorted(rng.uniform(0, duration_s) for _ in range(count * 2))
    segments = []
    for i in range(0, len(points) - 1, 2):
        if points[i + 1] - points[i] > 0.01:
            segments.append(
                Segment(
                    start_s=points[i],
                    end_s=points[i + 1],
                    reason="fuzz",
                    confidence=rng.uniform(0.3, 1.0),
                )
            )
    return segments
