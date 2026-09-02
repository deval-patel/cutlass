"""Unit tests for GLM provider response parsing — no network needed."""

import pytest

from app.models import FrameNote, Segment
from app.services.providers.glm import GLMProvider, _extract_json


@pytest.fixture
def provider():
    # Bypass the API-key check; these tests never make network calls.
    class _NoInit(GLMProvider):
        def __init__(self):
            pass

    return _NoInit()


def test_extract_json_plain():
    assert _extract_json('[{"a": 1}]') == [{"a": 1}]


def test_extract_json_in_code_fence():
    raw = '```json\n[{"a": 1}, {"b": 2}]\n```\nSome trailing prose.'
    assert _extract_json(raw) == [{"a": 1}, {"b": 2}]


def test_extract_json_with_surrounding_prose():
    raw = "Here is the result: [1, 2, 3] hope that helps!"
    assert _extract_json(raw) == [1, 2, 3]


def test_extract_json_missing_raises():
    with pytest.raises(ValueError):
        _extract_json("no array here")


def test_parse_note_validates_labels(provider):
    note = provider._parse_note({"t": 3.2, "description": "person talking", "label": "filler"})
    assert note == FrameNote(timestamp_s=3.2, description="person talking", label="filler")


def test_parse_note_unknown_label_falls_back(provider):
    note = provider._parse_note({"t": 1, "description": "?", "label": "garbage"})
    assert note.label == "other"


def test_analyze_frames_parses_model_array(provider, monkeypatch, tmp_path):
    frames = [(0.0, tmp_path / "f0.jpg"), (2.0, tmp_path / "f1.jpg")]
    for _, p in frames:
        p.write_bytes(b"x")
    captured = {}

    def fake_chat(model, messages):
        captured["model"] = model
        captured["content"] = messages[0]["content"]
        return '[{"t": 0.0, "description": "intro card", "label": "intro_outro"}, \
                 {"t": 2.0, "description": "talking head", "label": "core"}]'

    monkeypatch.setattr(provider, "_chat", fake_chat)
    notes = provider.analyze_frames(frames, 10.0)

    assert [n.label for n in notes] == ["intro_outro", "core"]
    # The request must carry the frames as base64 images with timestamps.
    kinds = [c["type"] for c in captured["content"]]
    assert kinds.count("image_url") == 2
    texts = [c["text"] for c in captured["content"] if c["type"] == "text"]
    assert any("t=0.0" in t for t in texts)


def test_select_segments_clamps_and_filters(provider, monkeypatch):
    def fake_chat(model, messages):
        prompt = messages[0]["content"]
        assert "60s" in prompt  # duration is conveyed to the model
        return '[{"start_s": -5, "end_s": 10, "reason": "clamp start", "confidence": 0.9}, \
                 {"start_s": 20, "end_s": 15, "reason": "inverted", "confidence": 0.9}, \
                 {"start_s": 50, "end_s": 999, "reason": "clamp end", "confidence": 0.8}]'

    monkeypatch.setattr(provider, "_chat", fake_chat)
    notes = [
        FrameNote(timestamp_s=float(i), description=f"note {i}", label="core") for i in range(10)
    ]
    segments = provider.select_segments(notes, total_duration_s=60.0)

    assert [(s.start_s, s.end_s) for s in segments] == [(0.0, 10.0), (50.0, 60.0)]
    assert all(isinstance(s, Segment) for s in segments)
