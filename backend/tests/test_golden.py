"""Golden replay harness (Plan 2): recorded model responses are pushed
through coercion + enforcement and compared against hand-approved cuts.

A prompt-template or enforcement change that shifts selection semantics
shows up here as an IoU / retention / pacing regression — without any
network calls. Add real fixtures by recording a response (the raw text)
from an actual run next to the hand-approved cut for that footage.
"""

import json
from pathlib import Path

import pytest

from app.models import Segment, TranscriptLine
from app.services.providers.glm import _coerce_segments, _extract_json
from app.styles import enforcement as enf
from app.styles import metrics
from app.styles.presets import load_preset

GOLDEN_DIR = Path(__file__).parent / "golden"
fixtures = sorted(GOLDEN_DIR.glob("*.json"))
assert fixtures, "golden fixture directory must not be empty"


@pytest.mark.parametrize("fixture_path", fixtures, ids=lambda p: p.stem)
def test_golden_replay(fixture_path: Path):
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    style = load_preset(doc["style"])
    duration = doc["source_duration_s"]
    transcript = [TranscriptLine.model_validate(t) for t in doc["transcript"]]
    golden = [Segment.model_validate(g) for g in doc["golden_cut"]]

    segments = _coerce_segments(_extract_json(doc["recorded_response"]), duration)
    final = enf.enforce_segments(segments, style, duration, transcript)

    assert not enf.violates_hard_constraints(final, style)
    assert all(s.end_s <= duration + 1e-9 for s in final)

    expectations = doc["expectations"]
    iou = metrics.selection_iou(final, golden)
    assert iou >= expectations["min_selection_iou"], f"selection drifted: IoU {iou:.3f}"
    assert metrics.avg_segment_s(final) <= expectations["max_avg_segment_s"] + 1e-9

    # Retention is a soft target: enforcement can't fix it (only the model
    # can, via the feedback re-prompt — not replayable from a recording), so
    # it is reported, not asserted.
    retention = metrics.retention(final, duration)
    print(f"  {fixture_path.stem}: IoU {iou:.3f}, retention {retention:.1%}, {len(final)} segments")
