from app.models import Segment
from app.services.edl import normalize_segments


def seg(start, end, reason="r"):
    return Segment(start_s=start, end_s=end, reason=reason)


def test_sorts_out_of_order():
    result = normalize_segments([seg(10, 15), seg(0, 5)], 100)
    assert [(s.start_s, s.end_s) for s in result] == [(0, 5), (10, 15)]


def test_merges_overlaps_and_adjacent():
    result = normalize_segments([seg(0, 5), seg(4, 8), seg(8.02, 12)], 100)
    assert [(s.start_s, s.end_s) for s in result] == [(0, 12)]


def test_clamps_to_duration():
    result = normalize_segments([seg(90, 200)], 100)
    assert [(s.start_s, s.end_s) for s in result] == [(90, 100)]


def test_drops_tiny_and_inverted_segments():
    result = normalize_segments([seg(5, 5.01), seg(8, 3), seg(1, 2)], 100)
    assert [(s.start_s, s.end_s) for s in result] == [(1, 2)]


def test_swapped_bounds_are_dropped_not_flipped():
    # A swapped pair means the user error should shrink to nothing, not silently flip.
    result = normalize_segments([seg(30, 10)], 100)
    assert result == []
