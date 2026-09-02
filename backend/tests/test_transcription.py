from pathlib import Path

from app.models import TranscriptLine
from app.services import ffmpeg
from app.services.providers.dry import DryRunProvider


def test_dry_run_transcript_in_job(client, test_video):
    from conftest import upload_and_wait

    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")

    transcript = job["transcript"]
    assert len(transcript) >= 1
    # Dry run: one 30s line per chunk — a 10s video gets a single line.
    assert transcript[0]["start_s"] == 0.0
    assert transcript[0]["end_s"] == 10.0
    assert "dry run" in transcript[0]["text"]


def test_transcription_failure_does_not_block_analysis(client, test_video, monkeypatch):
    """Audio is a bonus signal — pipeline must survive a broken transcriber."""
    from conftest import upload_and_wait

    import app.services.analyzer as analyzer

    class Exploding:
        def transcribe(self, audio, duration_s):
            raise RuntimeError("endpoint down")

    original = analyzer.get_provider

    def broken_provider():
        provider = original()
        provider.transcribe = Exploding().transcribe
        return provider

    monkeypatch.setattr(analyzer, "get_provider", broken_provider)

    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")
    assert job["transcript"] == []


def test_dry_run_transcriber_covers_duration():
    provider = DryRunProvider()
    lines = provider.transcribe(Path("x.wav"), 75.0)
    assert [(ln.start_s, ln.end_s) for ln in lines] == [(0.0, 30.0), (30.0, 60.0), (60.0, 75.0)]


def test_glm_transcriber_parses_verbose_json(monkeypatch, tmp_path):
    from app.services.providers.glm import GLMProvider

    class _NoInit(GLMProvider):
        def __init__(self):
            self._headers = {}

    provider = _NoInit()

    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"riff")

    def fake_post(url, **kwargs):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "segments": [
                        {"start": 0.0, "end": 2.5, "text": " hello world"},
                        {"start": 2.5, "end": 5.0, "text": "   "},  # blank → dropped
                    ]
                }

        return R()

    monkeypatch.setattr("app.services.providers.glm.httpx.post", fake_post)

    lines = provider.transcribe(wav, 600.0)
    assert lines == [TranscriptLine(start_s=0.0, end_s=2.5, text="hello world")]


def test_glm_transcriber_plain_text_fallback(monkeypatch, tmp_path):
    from app.services.providers.glm import GLMProvider

    class _NoInit(GLMProvider):
        def __init__(self):
            self._headers = {}

    provider = _NoInit()
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"riff")

    def fake_post(url, **kwargs):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"text": "whole clip text"}

        return R()

    monkeypatch.setattr("app.services.providers.glm.httpx.post", fake_post)

    lines = provider.transcribe(wav, 120.0)
    assert lines == [TranscriptLine(start_s=0.0, end_s=120.0, text="whole clip text")]


def test_glm_select_segments_prompt_includes_transcript(monkeypatch, tmp_path):
    from app.models import FrameNote
    from app.services.providers.glm import GLMProvider

    class _NoInit(GLMProvider):
        def __init__(self):
            pass

    provider = _NoInit()

    captured = {}

    def fake_chat(model, messages):
        captured["prompt"] = messages[0]["content"]
        return '[{"start_s": 0, "end_s": 5, "reason": "r", "confidence": 1.0}]'

    monkeypatch.setattr(provider, "_chat", fake_chat)

    notes = [FrameNote(timestamp_s=1.0, description="talking", label="core")]
    transcript = [TranscriptLine(start_s=0.0, end_s=4.0, text="welcome to the video")]
    provider.select_segments(notes, 10.0, transcript)

    prompt = captured["prompt"]
    assert "welcome to the video" in prompt
    assert "[0.0-4.0s]" in prompt

    # And without a transcript the section is absent.
    provider.select_segments(notes, 10.0, [])
    assert "Transcript:" not in captured["prompt"]


def test_extract_audio_slice(test_video, tmp_path):
    wav = ffmpeg.extract_audio(test_video, tmp_path / "a.wav", start_s=2.0, duration_s=3.0)
    assert wav.exists() and wav.stat().st_size > 1000
    # 16kHz mono 16-bit PCM: ~3s ≈ 96kB + header.
    assert wav.stat().st_size < 200_000
