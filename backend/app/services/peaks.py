"""Audio waveform peaks (Plan 3): computed once per asset, cached to disk.

The editor's waveform lane renders min/max amplitude buckets. We decode a
mono 8 kHz PCM track with ffmpeg and bucket it at ~100 ms resolution —
36k entries for an hour of footage, compact enough to serve as JSON.
Cached inside the asset's directory, so project deletion cleans it up.
"""

import json
import logging
import struct
import subprocess
from pathlib import Path
from typing import Any

from .. import config

logger = logging.getLogger(__name__)

# ~100 ms per bucket at 8 kHz mono.
_SAMPLES_PER_BUCKET = 800
_PEAK_CAP = 250_000  # safety valve for pathological durations


def peaks_path(asset_id: str) -> Path:
    return config.UPLOADS_DIR / asset_id / "peaks.json"


def compute_peaks(asset_id: str) -> dict[str, Any]:
    """Decode the asset's audio and bucket into [min, max] pairs (0..1)."""
    source = config.UPLOADS_DIR / asset_id / "source.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "a:0?",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"audio decode failed: {proc.stderr[-300:].decode(errors='replace')}")
    pcm = proc.stdout
    step = _SAMPLES_PER_BUCKET * 2  # 16-bit samples
    buckets: list[list[float]] = []
    for offset in range(0, len(pcm) - 1, step):
        chunk = pcm[offset : offset + step]
        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        lo = min(samples) / 32768.0
        hi = max(samples) / 32768.0
        buckets.append([round(lo, 3), round(hi, 3)])
        if len(buckets) >= _PEAK_CAP:
            logger.warning("peaks capped at %d buckets for %s", _PEAK_CAP, asset_id)
            break
    duration_s = len(buckets) / 10.0  # 10 buckets per second
    return {"bucket_seconds": 0.1, "buckets": buckets, "duration_s": round(duration_s, 2)}


def get_peaks(asset_id: str) -> dict[str, Any]:
    """Cached accessor: compute on first request, serve from disk afterwards."""
    cache = peaks_path(asset_id)
    if cache.exists():
        parsed: dict[str, Any] = json.loads(cache.read_text())
        return parsed
    peaks = compute_peaks(asset_id)
    cache.write_text(json.dumps(peaks))
    return peaks
