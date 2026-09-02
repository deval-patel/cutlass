"""EditStyle spec + preset library (Plan 2)."""

import pytest

from app.styles import presets
from app.styles.models import EditStyle


def test_every_preset_file_loads_and_matches_its_id():
    files = sorted(presets.PRESETS_DIR.glob("*.json"))
    assert len(files) >= 5, "preset library should not silently empty out"
    listed = {p.preset_id: p for p in presets.list_presets()}
    for path in files:
        style = presets.load_preset(path.stem)
        assert style.preset_id == path.stem
        assert path.stem in listed
        assert listed[path.stem].name
        assert listed[path.stem].description


def test_default_preset_is_baseline_parity():
    style = presets.load_preset("default")
    # No numeric opinions: the default style must not change current behavior.
    assert style.target_retention is None
    assert style.target_segment_len_s is None
    assert style.min_segment_s is None
    assert style.max_segment_s is None
    assert style.max_segment_count is None


def test_preset_knobs_carry_the_editorial_intent():
    shorts = presets.load_preset("shorts")
    assert shorts.max_segment_s == 12.0
    assert shorts.target_retention == pytest.approx(0.35)
    assert shorts.cut_on == "sentence"

    cinematic = presets.load_preset("cinematic")
    assert cinematic.min_segment_s == 8.0
    assert cinematic.cut_on == "shot"


def test_resolve_style_layers_brief_and_tolerates_unknown_preset():
    style = presets.resolve_style("shorts", "  cut on every drum hit  ")
    assert style.preset_id == "shorts"
    assert style.user_brief == "cut on every drum hit"

    fallback = presets.resolve_style("does-not-exist", None)
    assert fallback.preset_id == "default"
    assert fallback.user_brief == ""


def test_hard_constraints_text_renders_enforceables():
    style = presets.load_preset("shorts")
    text = style.hard_constraints_text()
    assert "12s" in text and "25 keep-segments" in text
    assert "35%" in text
    assert "sentence" in text

    assert EditStyle(preset_id="default").hard_constraints_text() == "No hard pacing constraints."


def test_presets_endpoint_lists_the_gallery(client):
    res = client.get("/api/v1/styles")
    assert res.status_code == 200
    presets = res.json()
    ids = [p["preset_id"] for p in presets]
    assert "default" in ids and "shorts" in ids and "cinematic" in ids
    assert all({"preset_id", "name", "description", "pacing"} <= set(p) for p in presets)
