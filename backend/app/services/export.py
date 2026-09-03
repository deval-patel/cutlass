"""Timeline exports (Plan 3): SRT captions, FCPXML, CMX3600 EDL.

Hand-rolled generators for the single-asset cut timelines this version
produces — no OpenTimelineIO dependency. These are the standard
interchange targets (Resolve/Premiere/FCP import FCPXML and EDL; SRT is
universal). Multi-asset exports arrive with Plan 4 and reuse these
writers per track.
"""

import math

from ..models import TranscriptLine
from ..timelines import schema as timeline_schema
from ..timelines.schema import Timeline

_EPS = 1e-9


def _video_clips(timeline: Timeline) -> list[timeline_schema.Clip]:
    track = next((t for t in timeline.tracks if t.kind == "video"), None)
    if track is None:
        return []
    return sorted((c for c in track.clips if c.enabled), key=lambda c: c.record_start_s)


def _require_single_asset(timeline: Timeline) -> str:
    asset_ids = {clip.source.asset_id for clip in _video_clips(timeline)}
    if not asset_ids:
        raise ValueError("timeline has no clips to export")
    if len(asset_ids) > 1:
        raise ValueError("multi-asset export arrives with multi-asset timelines")
    return next(iter(asset_ids))


def _tc(seconds: float, fps: float) -> str:
    """SMPTE timecode HH:MM:SS:FF (non-drop)."""
    fps = max(1.0, fps)
    frames_per_second = round(fps)
    total_frames = round(seconds * fps)
    f = total_frames % frames_per_second
    total_seconds = total_frames // frames_per_second
    s = total_seconds % 60
    m = (total_seconds // 60) % 60
    h = total_seconds // 3600
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def _rational(seconds: float, fps: float) -> str:
    """FCPXML rational time, frame-aligned and reduced (e.g. '2/5s')."""
    frames = round(seconds * fps)
    base = round(fps)
    divisor = math.gcd(int(frames), base) or 1
    return f"{int(frames) // divisor}/{base // divisor}s"


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def export_srt(timeline: Timeline, transcript: list[TranscriptLine]) -> str:
    """Transcript lines re-timed into record time, kept ranges only.

    Lines are clipped to keep-ranges and split at cuts, so no caption
    survives inside a removed range.
    """
    clips = _video_clips(timeline)
    _require_single_asset(timeline)
    cue_id = 0
    out: list[str] = []
    for line in sorted(transcript, key=lambda ln: ln.start_s):
        for clip in clips:
            lo = max(line.start_s, clip.source.in_s)
            hi = min(line.end_s, clip.source.out_s)
            if hi - lo <= 0.05:
                continue
            shift = clip.record_start_s - clip.source.in_s
            cue_id += 1
            start = lo + shift
            end = hi + shift
            out.append(f"{cue_id}\n{_srt_time(start)} --> {_srt_time(end)}\n{line.text}\n")
    return "\n".join(out)


def _srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_fcpxml(timeline: Timeline, asset_filename: str, name: str) -> str:
    """Minimal FCPXML 1.9: one event, one spine, video-only asset cuts."""
    _require_single_asset(timeline)
    clips = _video_clips(timeline)
    if not clips:
        raise ValueError("timeline has no clips to export")
    fps = timeline.frame_rate or 30.0
    total = timeline_schema.duration_s(timeline)

    resources = [
        f'<format id="r1" frameDuration="{_rational(1 / fps, fps)}" '
        'name="FFVideoFormatRateUndefined" />',
        f'<asset id="r2" name="{_esc(asset_filename)}" src="./{_esc(asset_filename)}" '
        f'hasVideo="1" format="r1" />',
    ]
    spine = []
    offset = 0.0
    for clip in clips:
        duration = clip.source.out_s - clip.source.in_s
        spine.append(
            f'<asset-clip ref="r2" name="{_esc(clip.name or asset_filename)}" '
            f'offset="{_rational(offset, fps)}" start="{_rational(clip.source.in_s, fps)}" '
            f'duration="{_rational(duration, fps)}" />'
        )
        offset += duration

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        '<fcpxml version="1.9">\n'
        "  <resources>\n    " + "\n    ".join(resources) + "\n  </resources>\n"
        f'  <project id="p1" name="{_esc(name)}">\n'
        f'    <sequence id="s1" format="r1" duration="{_rational(total, fps)}">\n'
        "      <spine>\n        " + "\n        ".join(spine) + "\n      </spine>\n"
        "    </sequence>\n"
        "  </project>\n"
        "</fcpxml>\n"
    )


def export_edl(timeline: Timeline, name: str, fps: float = 30.0) -> str:
    """CMX3600-style EDL (video-only, one track, straight cuts)."""
    _require_single_asset(timeline)
    clips = _video_clips(timeline)
    if not clips:
        raise ValueError("timeline has no clips to export")
    lines = [f"TITLE: {name.upper()}", "FCM: NON-DROP FRAME", ""]
    record = 0.0
    for i, clip in enumerate(clips, start=1):
        duration = clip.source.out_s - clip.source.in_s
        lines.append(
            f"{i:03d}  AX       V     C        "
            f"{_tc(clip.source.in_s, fps)} {_tc(clip.source.out_s, fps)} "
            f"{_tc(record, fps)} {_tc(record + duration, fps)}"
        )
        comment = clip.reason or clip.name
        if comment:
            lines.append(f"* FROM CLIP NAME: {comment}")
        lines.append("")
        record += duration
    return "\n".join(lines)
