import json
import subprocess
from pathlib import Path

from ..models import VideoMeta


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


def probe(path: Path) -> VideoMeta:
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
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
    proc = _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{interval_s},scale={width}:-2",
            "-q:v",
            "4",
            str(out_dir / "frame_%06d.jpg"),
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"frame extraction failed: {proc.stderr[-500:]}")
    frames = sorted(out_dir.glob("frame_*.jpg"))
    # ffmpeg names frames 1..N at t = (n-1) * interval_s
    return [((i) * interval_s, p) for i, p in enumerate(frames)]


def extract_audio(
    video: Path, out_path: Path, start_s: float | None = None, duration_s: float | None = None
) -> Path:
    """Extract 16kHz mono WAV (optionally a time slice) for transcription."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-y"]
    if start_s is not None:
        args += ["-ss", f"{start_s:.3f}"]
    if duration_s is not None:
        args += ["-t", f"{duration_s:.3f}"]
    args += [
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    proc = _run(args)
    if proc.returncode != 0:
        raise RuntimeError(f"audio extraction failed: {proc.stderr[-500:]}")
    return out_path


def render_timeline(clip_specs: list[tuple[Path, float, float]], out_path: Path) -> None:
    """Render a timeline: trim each (video, source_in, source_out) clip and
    concatenate in record order. One input per unique video, so multi-asset
    timelines render exactly like single-asset ones (same duration parity).
    """
    if not clip_specs:
        raise RuntimeError("no clips to render")

    inputs: list[Path] = []
    input_index: dict[str, int] = {}
    for video, _, _ in clip_specs:
        key = str(video)
        if key not in input_index:
            input_index[key] = len(inputs)
            inputs.append(video)

    filters: list[str] = []
    concat_refs: list[str] = []
    for j, (video, source_in, source_out) in enumerate(clip_specs):
        if source_out - source_in <= 0:
            raise RuntimeError(f"clip {j} has an empty source range")
        input_idx = input_index[str(video)]
        filters.append(
            f"[{input_idx}:v]trim=start={source_in:.3f}:end={source_out:.3f},"
            f"setpts=PTS-STARTPTS[v{j}]"
        )
        filters.append(
            f"[{input_idx}:a]atrim=start={source_in:.3f}:end={source_out:.3f},"
            f"asetpts=PTS-STARTPTS[a{j}]"
        )
        concat_refs.append(f"[v{j}][a{j}]")

    graph = (
        ";".join(filters) + f";{''.join(concat_refs)}concat=n={len(clip_specs)}:v=1:a=1[v][aout]"
    )

    args = ["ffmpeg", "-y"]
    for video in inputs:
        args += ["-i", str(video)]
    args += [
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    proc = _run(args)
    if proc.returncode != 0:
        raise RuntimeError(f"render failed: {proc.stderr[-500:]}")
