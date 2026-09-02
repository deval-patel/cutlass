"""Deterministic enforcement (Plan 2): hard constraints hold no matter what
the model returns, and cut points snap to sentence boundaries."""

import random

import pytest

from app.models import Segment, TranscriptLine
from app.styles import enforcement as enf
from app.styles import metrics
from app.styles.presets import load_preset, resolve_style


def _seg(start: float, end: float, reason: str = "r") -> Segment:
    return Segment(start_s=start, end_s=end, reason=reason, confidence=0.9)


def test_default_style_is_passthrough():
    style = load_preset("default")
    draft = [_seg(1.0, 50.0)]
    assert enf.enforce_segments(draft, style, 60.0) == draft


def test_max_segment_length_splits_at_sentence_boundaries():
    style = load_preset("shorts")  # max 12s
    transcript = [
        TranscriptLine(start_s=10.0, end_s=14.0, text="one"),
        TranscriptLine(start_s=14.0, end_s=24.0, text="two"),
    ]
    draft = [_seg(10.0, 34.0)]
    out = enf.enforce_segments(draft, style, 40.0, transcript)
    assert all(s.end_s - s.start_s <= 12.0 + 1e-9 for s in out)
    assert sum(s.end_s - s.start_s for s in out) == pytest.approx(24.0)
    # A split point landed on the 14s sentence boundary (within 3s of ideal).
    assert any(abs(s.end_s - 14.0) < 1e-6 or abs(s.start_s - 14.0) < 1e-6 for s in out)


def test_min_segment_length_folds_stubs():
    style = load_preset("cinematic")  # min 8s
    draft = [_seg(0.0, 20.0), _seg(20.0, 22.0), _seg(22.0, 50.0)]
    out = enf.enforce_segments(draft, style, 60.0)
    assert all(s.end_s - s.start_s >= 8.0 - 1e-9 for s in out)
    assert sum(s.end_s - s.start_s for s in out) == pytest.approx(50.0)


def test_segment_count_cap_merges_shortest_pairs():
    style = load_preset("b_roll")  # cap 60
    draft = [_seg(float(i) * 2.0, float(i) * 2.0 + 1.9) for i in range(80)]
    out = enf.enforce_segments(draft, style, 200.0)
    assert len(out) <= 60
    # The cap respects min/max feasibility (b_roll max 10s, duration 200s
    # needs >= 20 segments — we got well above that, all constraints hold).


def test_infeasible_cap_yields_to_min_max():
    # duration 600s with max 60s needs >= 10 segments; cap 5 is impossible.
    style = resolve_style("default", None).model_copy(
        update={"max_segment_s": 60.0, "max_segment_count": 5, "cut_on": "anywhere"}
    )
    draft = [_seg(float(i) * 60.0, float(i + 1) * 60.0) for i in range(10)]
    out = enf.enforce_segments(draft, style, 600.0)
    assert all(s.end_s - s.start_s <= 60.0 + 1e-9 for s in out)
    assert len(out) == 10  # cap impossible; min/max win


def test_boundaries_snap_to_sentences_within_tolerance():
    style = resolve_style("default", None).model_copy(update={"cut_on": "sentence"})
    transcript = [
        TranscriptLine(start_s=9.4, end_s=10.2, text="...ends here"),
        TranscriptLine(start_s=10.2, end_s=30.0, text="next thought"),
    ]
    draft = [_seg(10.5, 30.0)]  # 10.5 starts mid-sentence; 10.2 is 0.3s away
    out = enf.enforce_segments(draft, style, 40.0, transcript)
    assert out[0].start_s == pytest.approx(10.2)


def test_messy_model_output_is_repaired():
    style = load_preset("shorts")
    messy = [
        _seg(5.0, 5.0),  # empty -> dropped by normalize
        _seg(-10.0, 30.0),  # clamps to 0
        _seg(25.0, 100.0),  # overlaps + exceeds duration -> clamp/merge
        _seg(300.0, 310.0),  # beyond duration -> dropped
    ]
    out = enf.enforce_segments(messy, style, 120.0)
    assert not enf.violates_hard_constraints(out, style)
    assert sum(s.end_s - s.start_s for s in out) <= 120.0


@pytest.mark.parametrize("seed", range(20))
def test_property_random_drafts_always_satisfy_hard_constraints(seed: int):
    rng = random.Random(seed)
    for preset_id in ("shorts", "cinematic", "documentary", "b_roll", "vlog", "travel_diary"):
        style = load_preset(preset_id)
        duration = rng.choice([45.0, 300.0, 1800.0])
        messy = enf.fuzz_segments(rng, duration, rng.randint(1, 30))
        out = enf.enforce_segments(messy, style, duration)
        assert not enf.violates_hard_constraints(out, style), (
            f"{preset_id} seed={seed}: {[(s.start_s, s.end_s) for s in out]}"
        )


def test_metrics_iou_retention_pacing():
    a = [_seg(0.0, 10.0), _seg(20.0, 30.0)]
    assert metrics.selection_iou(a, a) == pytest.approx(1.0)
    assert metrics.selection_iou(a, [_seg(0.0, 10.0)]) == pytest.approx(0.5)
    assert metrics.retention(a, 100.0) == pytest.approx(0.2)
    assert metrics.avg_segment_s(a) == pytest.approx(10.0)

    shorts = load_preset("shorts")
    assert metrics.pacing_deviation([_seg(0.0, 6.0)], shorts) == pytest.approx(0.0)
    assert metrics.pacing_deviation([_seg(0.0, 12.0)], shorts) == pytest.approx(1.0)
    assert metrics.retention_delta([_seg(0.0, 50.0)], shorts, 100.0) == pytest.approx(0.15)


def test_retention_feedback_message_only_when_off_target():
    shorts = load_preset("shorts")
    assert enf.retention_feedback(shorts, 0.40) is None  # within ±20pts
    text = enf.retention_feedback(shorts, 0.90)
    assert text is not None and "Select less footage" in text
    assert enf.retention_feedback(shorts, 0.05) is not None
    assert enf.retention_feedback(load_preset("default"), 0.99) is None
