from ..models import Segment

# Segments closer than this get merged into one.
MERGE_GAP_S = 0.05
# Segments shorter than this are dropped as editing noise.
MIN_SEGMENT_S = 0.05


def normalize_segments(segments: list[Segment], duration_s: float) -> list[Segment]:
    """Clamp to [0, duration], drop empties, sort, merge overlaps/adjacency."""
    cleaned = []
    for s in segments:
        start = max(0.0, min(s.start_s, duration_s))
        end = max(0.0, min(s.end_s, duration_s))
        if end - start >= MIN_SEGMENT_S:
            cleaned.append(Segment(
                start_s=start, end_s=end, reason=s.reason, confidence=s.confidence,
            ))
    cleaned.sort(key=lambda s: s.start_s)
    merged: list[Segment] = []
    for s in cleaned:
        if merged and s.start_s <= merged[-1].end_s + MERGE_GAP_S:
            merged[-1].end_s = max(merged[-1].end_s, s.end_s)
        else:
            merged.append(s)
    return merged
