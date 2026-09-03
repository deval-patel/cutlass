"""Timeline exports: SRT captions, FCPXML, CMX3600 EDL.

Hand-rolled generators — no OpenTimelineIO dependency. These are the
standard interchange targets (Resolve/Premiere/FCP import FCPXML and
EDL; SRT is universal). Multi-asset timelines are first-class: FCPXML
emits one resource per referenced asset, EDL events carry a reel name
derived from the asset id, and SRT merges transcripts per asset.
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


def _asset_ids(timeline: Timeline) -> list[str]:
    """Unique asset ids in clip order; error when the timeline is empty."""
    ids: list[str] = []
    for clip in _video_clips(timeline):
        if clip.source.asset_id not in ids:
            ids.append(clip.source.asset_id)
    if not ids:
        raise ValueError("timeline has no clips to export")
    return ids


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


def export_srt(timeline: Timeline, transcripts: dict[str, list[TranscriptLine]]) -> str:
    """Transcript lines re-timed into record time, kept ranges only.

    Lines are clipped to keep-ranges and split at cuts, so no caption
    survives inside a removed range. Assets without a transcript
    contribute no cues.
    """
    clips = _video_clips(timeline)
    _asset_ids(timeline)
    cue_id = 0
    out: list[str] = []
    for asset_id, transcript in transcripts.items():
        for line in sorted(transcript, key=lambda ln: ln.start_s):
            for clip in clips:
                if clip.source.asset_id != asset_id:
                    continue
                lo = max(line.start_s, clip.source.in_s)
                hi = min(line.end_s, clip.source.out_s)
                if hi - lo <= 0.05:
                    continue
                shift = clip.record_start_s - clip.source.in_s
                cue_id += 1
                out.append(
                    f"{cue_id}\n{_srt_time(lo + shift)} --> {_srt_time(hi + shift)}\n{line.text}\n"
                )
    return "\n".join(out)


def _srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_fcpxml(timeline: Timeline, asset_filenames: dict[str, str], name: str) -> str:
    """Minimal FCPXML 1.9: one event, one spine, video-only asset cuts.

    asset_filenames maps asset_id -> file name; one resource is emitted
    per referenced asset.
    """
    clips = _video_clips(timeline)
    ids = _asset_ids(timeline)
    fps = timeline.frame_rate or 30.0
    total = timeline_schema.duration_s(timeline)

    resources = [
        f'<format id="r1" frameDuration="{_rational(1 / fps, fps)}" '
        'name="FFVideoFormatRateUndefined" />'
    ]
    rid_by_asset: dict[str, str] = {}
    for i, asset_id in enumerate(ids):
        rid = f"r{i + 2}"
        rid_by_asset[asset_id] = rid
        filename = asset_filenames.get(asset_id, f"{asset_id}.mp4")
        resources.append(
            f'<asset id="{rid}" name="{_esc(filename)}" src="./{_esc(filename)}" '
            f'hasVideo="1" format="r1" />'
        )

    spine = []
    offset = 0.0
    transition_count = 0
    for i, clip in enumerate(clips):
        duration = clip.source.out_s - clip.source.in_s
        default_name = asset_filenames.get(clip.source.asset_id, clip.id)
        spine.append(
            f'<asset-clip ref="{rid_by_asset[clip.source.asset_id]}" '
            f'name="{_esc(clip.name or default_name)}" '
            f'offset="{_rational(offset, fps)}" start="{_rational(clip.source.in_s, fps)}" '
            f'duration="{_rational(duration, fps)}" />'
        )
        offset = clip.record_start_s + duration
        if clip.transition_out is not None and i + 1 < len(clips):
            transition_count += 1
            rid = f"rt{transition_count}"
            resources.append(f'<transition id="{rid}" name="Cross Dissolve" type="Video" />')
            spine.append(
                f'<transition ref="{rid}" '
                f'offset="{_rational(offset - clip.transition_out.duration_s, fps)}" '
                f'duration="{_rational(clip.transition_out.duration_s, fps)}" />'
            )

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
    """CMX3600-style EDL (video-only, one track, straight cuts).

    Multi-source EDLs use a reel name per event — the first 8 characters
    of the asset id (the CMX3600 reel field is 8 characters); a
    single-source timeline keeps the conventional AX reel. Crossfades are
    marked with a comment at the junction: full CMX3600 dissolve event
    pairs are a deferred refinement (lossy, documented in the plan).
    """
    clips = _video_clips(timeline)
    ids = _asset_ids(timeline)
    single = len(ids) == 1
    lines = [f"TITLE: {name.upper()}", "FCM: NON-DROP FRAME", ""]
    record = 0.0
    for i, clip in enumerate(clips, start=1):
        duration = clip.source.out_s - clip.source.in_s
        reel = "AX" if single else clip.source.asset_id[:8].upper()
        lines.append(
            f"{i:03d}  {reel:<8} V     C        "
            f"{_tc(clip.source.in_s, fps)} {_tc(clip.source.out_s, fps)} "
            f"{_tc(record, fps)} {_tc(record + duration, fps)}"
        )
        comment = clip.reason or clip.name
        if comment:
            lines.append(f"* FROM CLIP NAME: {comment}")
        if clip.transition_out is not None:
            lines.append(
                f"* CROSSFADE {clip.transition_out.duration_s:.3f}s TO NEXT "
                "(exported as a cut — see FCPXML for the dissolve)"
            )
        lines.append("")
        record += duration
    return "\n".join(lines)
