"""Multi-asset timeline rendering (Plan 4 phase 1): per-clip trim + concat."""

import json
import subprocess
from pathlib import Path

import pytest
from conftest import wait_for_status


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def _make_clip(path: Path, seconds: int, hue: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={hue}:size=320x240:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={400 if hue == 'red' else 800}:duration={seconds}",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def test_render_timeline_concatenates_multiple_assets(tmp_path: Path):
    from app.services import ffmpeg

    red, blue = tmp_path / "red.mp4", tmp_path / "blue.mp4"
    _make_clip(red, 3, "red")
    _make_clip(blue, 3, "blue")

    # 2s of red, 2s of blue, 1s of red again — spans two inputs.
    specs = [(red, 0.0, 2.0), (blue, 0.0, 2.0), (red, 2.0, 3.0)]
    out = tmp_path / "final.mp4"
    ffmpeg.render_timeline(specs, out)

    assert probe_duration(out) == pytest.approx(5.0, abs=0.15)


def test_render_timeline_requires_clips(tmp_path: Path):
    from app.services import ffmpeg

    with pytest.raises(RuntimeError, match="no clips"):
        ffmpeg.render_timeline([], tmp_path / "x.mp4")


def test_multi_asset_project_render_parity(client, test_video):
    """Full API: two assets in one project, multi-clip timeline, render."""
    project = client.post("/api/v1/projects", json={"name": "two-clip trip"}).json()

    ids = []
    for i in range(2):
        with test_video.open("rb") as f:
            res = client.post(
                f"/api/v1/projects/{project['id']}/assets",
                files={"video": (f"day{i + 1}.mp4", f)},
            )
        assert res.status_code == 200, res.text
        ids.append(res.json()["id"])

    for asset_id in ids:
        job = wait_for_status(client, asset_id, {"ready", "failed"})
        assert job["status"] == "ready", job.get("error")

    # Both drafts auto-assembled onto one timeline (asset 2 appended after
    # asset 1 by sync). Editor-style edit: halve asset 1's first clip and
    # pull asset 2's first clip up to close the gap.
    current = client.get(f"/api/v1/projects/{project['id']}/timeline").json()
    doc = current["document"]
    clips = doc["tracks"][0]["clips"]
    a1 = next(c for c in clips if c["source"]["asset_id"] == ids[0])
    a2 = next(c for c in clips if c["source"]["asset_id"] == ids[1])
    half = (a1["source"]["out_s"] - a1["source"]["in_s"]) / 2
    a1["source"]["out_s"] = a1["source"]["in_s"] + half
    a2["record_start_s"] = half
    doc["tracks"][0]["clips"] = [a1, a2]
    put = client.put(f"/api/v1/projects/{project['id']}/timeline", json=doc)
    assert put.status_code == 200, put.text

    assert client.post(f"/api/v1/assets/{ids[0]}/render").status_code == 200
    final = wait_for_status(client, ids[0], {"rendered", "failed"})
    assert final["status"] == "rendered", final.get("error")

    from app.config import UPLOADS_DIR
    from tests.test_api_edl import probe_duration  # reuse helper

    a2_span = a2["source"]["out_s"] - a2["source"]["in_s"]
    expected = half + a2_span
    duration = probe_duration(UPLOADS_DIR / ids[0] / "final_cut.mp4")
    assert duration == pytest.approx(expected, abs=0.2)
