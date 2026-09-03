"""Audio waveform peaks: computation, caching, endpoint contract."""

import json
import struct
from pathlib import Path

import pytest

from app.services import peaks


def _write_wav(path: Path, pcm: bytes) -> None:
    """Minimal 8 kHz mono PCM WAV wrapper."""
    import wave

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(pcm)


def test_compute_peaks_buckets_amplitude(tmp_path: Path, monkeypatch):
    from app import config

    asset_id = "pk1"
    asset_dir = config.UPLOADS_DIR / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    # 3 seconds: first second loud, middle silent, last second loud.
    loud = struct.pack("<8000h", *([24000] * 8000))
    silent = b"\x00\x00" * 8000
    _write_wav(asset_dir / "source.mp4", loud + silent + loud)

    monkeypatch.setattr(peaks, "peaks_path", lambda a: tmp_path / f"{a}.json")
    peaks_data = peaks.compute_peaks(asset_id)

    assert peaks_data["bucket_seconds"] == 0.1
    assert len(peaks_data["buckets"]) == 30
    assert peaks_data["duration_s"] == 3.0
    highs = [b for b in peaks_data["buckets"] if b[1] > 0.5]
    quiet = [b for b in peaks_data["buckets"] if b[1] < 0.05]
    assert len(highs) == 20 and len(quiet) == 10


def test_get_peaks_caches_to_disk(tmp_path: Path, monkeypatch):
    from app import config

    asset_id = "pk2"
    asset_dir = config.UPLOADS_DIR / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    _write_wav(asset_dir / "source.mp4", b"\x00\x00" * 16000)

    cache = tmp_path / f"{asset_id}.json"
    monkeypatch.setattr(peaks, "peaks_path", lambda a: cache)
    calls = {"n": 0}
    real = peaks.compute_peaks

    def counting(asset: str) -> dict:
        calls["n"] += 1
        return real(asset)

    monkeypatch.setattr(peaks, "compute_peaks", counting)
    peaks.get_peaks(asset_id)
    peaks.get_peaks(asset_id)
    assert calls["n"] == 1  # second request served from cache
    assert cache.exists()
    assert json.loads(cache.read_text())["bucket_seconds"] == 0.1


def test_peaks_endpoint_roundtrip(client, test_video):
    from conftest import upload_and_wait

    asset = upload_and_wait(client, test_video)
    res = client.get(f"/api/v1/assets/{asset['id']}/peaks")
    assert res.status_code == 200
    data = res.json()
    assert data["bucket_seconds"] == 0.1
    assert len(data["buckets"]) >= 90  # 10s video ≈ 100 buckets
    assert data["duration_s"] == pytest.approx(10.0, abs=0.5)

    # Second request hits the cache file on disk.
    from app.services import peaks as peaks_service

    assert peaks_service.peaks_path(asset["id"]).exists()
