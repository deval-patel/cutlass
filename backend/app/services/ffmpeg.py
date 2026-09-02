import json
import subprocess
from pathlib import Path

from ..models import VideoMeta


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


def probe(path: Path) -> VideoMeta:
    proc = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr[:500]}")
    data = json.loads(proc.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise RuntimeError("no video stream found")
    return VideoMeta(
        duration_s=float(data["format"].get("duration", 0)),
        fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate", "0")),
        width=int(video["width"]),
        height=int(video["height"]),
    )


def _parse_fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def extract_frames(
    video: Path, out_dir: Path, interval_s: float, width: int = 512
) -> list[tuple[float, Path]]:
    """Extract one frame every interval_s seconds, scaled to width.

    Returns sorted [(timestamp_s, jpeg_path), ...].
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = _run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps=1/{interval_s},scale={width}:-2",
        "-q:v", "4", str(out_dir / "frame_%06d.jpg"),
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"frame extraction failed: {proc.stderr[-500:]}")
    frames = sorted(out_dir.glob("frame_*.jpg"))
    # ffmpeg names frames 1..N at t = (n-1) * interval_s
    return [((i) * interval_s, p) for i, p in enumerate(frames)]


def render_cut(video: Path, segments: list[tuple[float, float]], out_path: Path) -> None:
    """Concatenate keep-segments into a single re-encoded mp4."""
    if not segments:
        raise RuntimeError("no segments to render")
    filter_parts = [
        f"(between(t,{start:.3f},{end:.3f}))" for start, end in segments
    ]
    expr = "+".join(filter_parts)
    vf = "select='" + expr + "',setpts=N/FRAME_RATE/TB"
    # Match select on the audio timeline too, then resync PTS.
    af = "aselect='" + expr + "',asetpts=N/SR/TB"
    proc = _run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", vf, "-af", af,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-movflags", "+faststart",
        str(out_path),
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"render failed: {proc.stderr[-500:]}")
