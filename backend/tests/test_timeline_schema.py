"""Timeline document schema: invariants, conversions, JSON round-trips."""

import pytest
from pydantic import ValidationError

from app.models import Segment
from app.timelines import schema


def _segments() -> list[Segment]:
    return [
        Segment(start_s=1.0, end_s=4.0, reason="opening", confidence=0.9),
        Segment(start_s=10.0, end_s=20.0, reason="main", confidence=0.8),
    ]


def test_from_segments_builds_contiguous_single_track():
    timeline = schema.from_segments(_segments(), asset_id="a1", frame_rate=30.0)

    assert len(timeline.tracks) == 1
    track = timeline.tracks[0]
    assert track.name == "V1" and track.kind == "video"
    (first, second) = track.clips
    # Record times are contiguous: 0..3 then 3..13.
    assert first.record_start_s == 0.0
    assert second.record_start_s == pytest.approx(3.0)
    assert (first.source.in_s, first.source.out_s) == (1.0, 4.0)
    assert first.reason == "opening"
    assert schema.duration_s(timeline) == pytest.approx(13.0)
    schema.validate(timeline)  # construction invariants hold


def test_segments_round_trip():
    timeline = schema.from_segments(_segments(), asset_id="a1")
    flat = schema.to_segments(timeline)
    assert [(s.start_s, s.end_s, s.reason) for s in flat] == [
        (1.0, 4.0, "opening"),
        (10.0, 20.0, "main"),
    ]


def test_json_round_trip_is_lossless():
    timeline = schema.from_segments(_segments(), asset_id="a1", frame_rate=24.0)
    parsed = schema.Timeline.model_validate_json(timeline.model_dump_json())
    assert parsed == timeline


def test_validate_rejects_overlapping_clips():
    timeline = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=0, out_s=10),
                        record_start_s=0,
                    ),
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=20, out_s=30),
                        record_start_s=5,  # overlaps the first clip's 0..10
                    ),
                ],
            )
        ]
    )
    with pytest.raises(ValueError, match="overlap"):
        schema.validate(timeline)


def test_validate_allows_overlaps_across_tracks():
    timeline = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=0, out_s=10),
                        record_start_s=0,
                    )
                ],
            ),
            schema.Track(
                name="A1",
                kind="audio",
                clips=[
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=0, out_s=10),
                        record_start_s=0,
                    )
                ],
            ),
        ]
    )
    schema.validate(timeline)  # tracks are independent lanes


def test_validate_rejects_duplicate_track_names_and_bad_ranges():
    dup = schema.Timeline(
        tracks=[
            schema.Track(name="V1", clips=[]),
            schema.Track(name="V1", clips=[]),
        ]
    )
    with pytest.raises(ValueError, match="duplicate track"):
        schema.validate(dup)

    empty_range = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[schema.Clip(source=schema.ClipSource(asset_id="a", in_s=5, out_s=5))],
            )
        ]
    )
    with pytest.raises(ValueError, match="source range is empty"):
        schema.validate(empty_range)

    bad_fps = schema.Timeline(frame_rate=0)
    with pytest.raises(ValueError, match="frame_rate"):
        schema.validate(bad_fps)


def test_disabled_clips_are_ignored_everywhere():
    timeline = schema.from_segments(_segments(), asset_id="a1")
    timeline.tracks[0].clips[1].enabled = False
    schema.validate(timeline)  # disabling cannot create overlaps
    assert schema.duration_s(timeline) == pytest.approx(3.0)
    assert schema.to_segments(timeline)[0].start_s == 1.0


def test_clip_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        schema.Clip(
            source=schema.ClipSource(asset_id="a", in_s=0, out_s=1),
            confidence=1.5,
        )
