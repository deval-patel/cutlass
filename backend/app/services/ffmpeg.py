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


def render_timeline(
    clip_specs: list[tuple[Path, float, float, float | None]],
    out_path: Path,
    fps: float | None = None,
) -> None:
    """Render a timeline: trim each clip and join clips in record order.

    Each spec is (video, source_in, source_out, xfade_to_next) where
    xfade_to_next is the crossfade duration to the FOLLOWING clip (None for
    a hard cut). Junctions with crossfades chain through xfade/acrossfade;
    hard-cut junctions split the timeline into runs that concat — one
    ffmpeg input per unique video either way.
    """
    if not clip_specs:
        raise RuntimeError("no clips to render")

    inputs: list[Path] = []
    input_index: dict[str, int] = {}
    for video, _, _, _ in clip_specs:
        key = str(video)
        if key not in input_index:
            input_index[key] = len(inputs)
            inputs.append(video)

    filters: list[str] = []

    # Group clips into runs joined by crossfades (a run ends at a hard cut).
    runs: list[list[tuple[Path, float, float, float | None]]] = [[clip_specs[0]]]
    for spec in clip_specs[1:]:
        if runs[-1][-1][3] is not None:
            runs[-1].append(spec)
        else:
            runs.append([spec])

    run_labels: list[tuple[str, str]] = []
    clip_index = 0
    for run in runs:
        video_labels: list[str] = []
        audio_labels: list[str] = []
        run_start = run[0][1]
        for video, source_in, source_out, _xfade in run:
            if source_out - source_in <= 0:
                raise RuntimeError(f"clip {clip_index} has an empty source range")
            input_idx = input_index[str(video)]
            v_label, a_label = f"v{clip_index}", f"a{clip_index}"
            # xfade requires constant-frame-rate inputs — normalize with
            # fps= after trim (frame-rate metadata is lost by setpts).
            video_chain = (
                f"[{input_idx}:v]trim=start={source_in:.3f}:end={source_out:.3f},"
                f"setpts=PTS-STARTPTS"
            )
            if fps:
                video_chain += f",fps={fps}"
            filters.append(f"{video_chain}[{v_label}]")
            # Normalize audio too: acrossfade needs matching rates/layout.
            filters.append(
                f"[{input_idx}:a]atrim=start={source_in:.3f}:end={source_out:.3f},"
                f"asetpts=PTS-STARTPTS,aresample=48000,"
                f"aformat=channel_layouts=stereo[{a_label}]"
            )
            video_labels.append(v_label)
            audio_labels.append(a_label)
            clip_index += 1

        # Chain crossfades within the run (video xfade + audio acrossfade).
        acc = video_labels[0]
        acc_a = audio_labels[0]
        for k in range(1, len(run)):
            xfade = run[k - 1][3]
            offset = run[k][1] - run_start
            x_out, ax_out = f"xv{clip_index}_{k}", f"xa{clip_index}_{k}"
            filters.append(
                f"[{acc}][{video_labels[k]}]xfade=transition=fade:"
                f"duration={xfade:.3f}:offset={offset:.3f}[{x_out}]"
            )
            filters.append(f"[{acc_a}][{audio_labels[k]}]acrossfade=d={xfade:.3f}[{ax_out}]")
            acc, acc_a = x_out, ax_out

        run_labels.append((acc, acc_a))

    if len(run_labels) == 1:
        v_out, a_out = run_labels[0]
    else:
        concat_refs = "".join(f"[{v}][{a}]" for v, a in run_labels)
        filters.append(f"{concat_refs}concat=n={len(run_labels)}:v=1:a=1[vout][aout]")
        v_out, a_out = "vout", "aout"

    graph = ";".join(filters)

    args = ["ffmpeg", "-y"]
    for video in inputs:
        args += ["-i", str(video)]
    args += [
        "-filter_complex",
        graph,
        "-map",
        f"[{v_out}]",
        "-map",
        f"[{a_out}]",
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
