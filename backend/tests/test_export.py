"""Timeline exports: SRT re-timing, FCPXML structure, CMX3600 EDL."""

import xml.etree.ElementTree as ET

import pytest

from app.models import Segment, TranscriptLine
from app.services import export
from app.timelines import schema as timeline_schema


def _timeline() -> timeline_schema.Timeline:
    segments = [
        Segment(start_s=12.0, end_s=40.0, reason="market", confidence=0.9),
        Segment(start_s=236.0, end_s=348.0, reason="food street", confidence=0.8),
    ]
    return timeline_schema.from_segments(segments, asset_id="a1", frame_rate=30.0)


def test_edl_structure_and_timecodes():
    edl = export.export_edl(_timeline(), "trip")
    lines = [ln for ln in edl.splitlines() if ln.strip()]
    assert lines[0] == "TITLE: TRIP"
    assert lines[1] == "FCM: NON-DROP FRAME"
    rec1 = lines[2]
    # Event 001, source 00:00:12:00 → 00:00:40:00, record 0 → 28s.
    assert rec1.startswith("001  AX       V     C")
    assert "00:00:12:00" in rec1 and "00:00:40:00" in rec1
    assert "00:00:00:00" in rec1 and "00:00:28:00" in rec1
    rec2 = lines[4]
    assert rec2.startswith("002")
    assert "00:03:56:00" in rec2  # 236s source in
    assert "00:00:28:00" in rec2  # record continues after event 1
    assert "* FROM CLIP NAME: food street" in edl


def test_fcpxml_is_valid_xml_with_expected_clips():
    xml = export.export_fcpxml(_timeline(), {"a1": "day1.mp4"}, "trip")
    root = ET.fromstring(xml)
    assert root.tag == "fcpxml"
    clips = root.findall("./project/sequence/spine/asset-clip")
    assert len(clips) == 2
    offsets = [c.get("offset") for c in clips]
    starts = [c.get("start") for c in clips]
    durations = [c.get("duration") for c in clips]
    # Frame-aligned, reduced rationals at 30fps (whole seconds reduce to /1s).
    assert offsets == ["0/1s", "28/1s"]
    assert starts == ["12/1s", "236/1s"]
    assert durations == ["28/1s", "112/1s"]
    # Every clip references the declared asset resource.
    assert all(c.get("ref") == "r2" for c in clips)
    assert root.find("./resources/asset") is not None


def test_fcpxml_total_duration_matches_timeline():
    timeline = _timeline()
    xml = export.export_fcpxml(timeline, {"a1": "day1.mp4"}, "trip")
    root = ET.fromstring(xml)
    sequence = root.find("./project/sequence")
    fps = 30
    total = timeline_schema.duration_s(timeline)
    assert sequence.get("duration") == export._rational(total, fps) == "140/1s"


def test_srt_retimes_into_record_time_and_clips_at_cuts():
    timeline = _timeline()
    transcript = [
        # Spans the first cut entirely (12-40 kept): clip to keep-range.
        TranscriptLine(start_s=10.0, end_s=20.0, text="crosses the cut"),
        TranscriptLine(start_s=100.0, end_s=140.0, text="fully removed"),
        TranscriptLine(start_s=240.0, end_s=250.0, text="inside second clip"),
    ]
    srt = export.export_srt(timeline, {"a1": transcript})

    assert "1\n00:00:00,000 --> 00:00:08,000\ncrosses the cut" in srt
    # 240s sits 4s into clip 2 (record start 28s) → 32s.
    assert "00:00:32,000 --> 00:00:42,000\ninside second clip" in srt
    assert "fully removed" not in srt
    # Caption inside a removed range must never appear.
    assert srt.count("-->") == 2


def test_exports_reject_empty_and_multi_asset_timelines():
    empty = timeline_schema.Timeline()
    with pytest.raises(ValueError, match="no clips"):
        export.export_edl(empty, "x")
    with pytest.raises(ValueError, match="no clips"):
        export.export_fcpxml(empty, "a.mp4", "x")
    with pytest.raises(ValueError, match="no clips"):
        export.export_srt(empty, {})

    multi = timeline_schema.Timeline(
        tracks=[
            timeline_schema.Track(
                name="V1",
                clips=[
                    timeline_schema.Clip(
                        source=timeline_schema.ClipSource(asset_id="a", in_s=0, out_s=5)
                    ),
                    timeline_schema.Clip(
                        source=timeline_schema.ClipSource(asset_id="b", in_s=0, out_s=5),
                        record_start_s=5,
                    ),
                ],
            )
        ]
    )
    timeline_schema.validate(multi)
    # Multi-asset is supported: reels per event, one resource per asset.
    edl = export.export_edl(multi, "x")
    assert any(ln.startswith("001  ") and "A" in ln.split()[1] for ln in edl.splitlines())
    xml = export.export_fcpxml(multi, {"a": "a.mp4", "b": "b.mp4"}, "x")
    assert xml.count("<asset ") == 2


def test_multi_asset_edl_uses_reel_names_per_asset():
    multi = timeline_schema.Timeline(
        tracks=[
            timeline_schema.Track(
                name="V1",
                clips=[
                    timeline_schema.Clip(
                        source=timeline_schema.ClipSource(asset_id="abcdefghij", in_s=0, out_s=5)
                    ),
                    timeline_schema.Clip(
                        source=timeline_schema.ClipSource(asset_id="zzzzzzzzzz", in_s=0, out_s=5),
                        record_start_s=5,
                    ),
                ],
            )
        ]
    )
    edl = export.export_edl(multi, "reels")
    reels = [ln.split()[1] for ln in edl.splitlines() if ln[:3].isdigit()]
    assert reels == ["ABCDEFGH", "ZZZZZZZZ"]


def test_export_endpoints_roundtrip(client, test_video):
    from conftest import upload_and_wait

    asset = upload_and_wait(client, test_video)
    project_id = asset["project_id"]

    for fmt in ("srt", "fcpxml", "edl"):
        res = client.get(f"/api/v1/projects/{project_id}/export/{fmt}")
        assert res.status_code == 200, (fmt, res.text)
        assert "attachment" in res.headers["content-disposition"]
        assert res.headers["content-disposition"].endswith(f'.{fmt}"')

    xml = client.get(f"/api/v1/projects/{project_id}/export/fcpxml").text
    ET.fromstring(xml)  # real draft timeline parses

    assert client.get(f"/api/v1/projects/{project_id}/export/wmv").status_code == 400
