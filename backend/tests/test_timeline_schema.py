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


def _crossfade_timeline() -> schema.Timeline:
    clips = [
        schema.Clip(source=schema.ClipSource(asset_id="a1", in_s=0, out_s=4), record_start_s=0),
        schema.Clip(
            source=schema.ClipSource(asset_id="a1", in_s=10, out_s=14), record_start_s=3
        ),  # overlaps 1s
    ]
    clips[0].transition_out = schema.Transition(type="crossfade", duration_s=1.0)
    timeline = schema.Timeline(frame_rate=30, tracks=[schema.Track(name="V1", clips=clips)])
    schema.validate(timeline)
    return timeline


def test_exact_transition_overlap_is_valid():
    timeline = _crossfade_timeline()
    # Total duration accounts for the overlap: 4 + 4 - 1.
    assert schema.duration_s(timeline) == pytest.approx(7.0)


def test_overlap_without_transition_is_rejected():
    timeline = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[
                    schema.Clip(source=schema.ClipSource(asset_id="a", in_s=0, out_s=4)),
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=10, out_s=14),
                        record_start_s=3,
                    ),
                ],
            )
        ]
    )
    with pytest.raises(ValueError, match="without a transition"):
        schema.validate(timeline)


def test_transition_duration_must_match_the_overlap():
    clips = [
        schema.Clip(source=schema.ClipSource(asset_id="a", in_s=0, out_s=4)),
        schema.Clip(
            source=schema.ClipSource(asset_id="a", in_s=10, out_s=14), record_start_s=3.5
        ),  # overlaps 0.5s
    ]
    clips[0].transition_out = schema.Transition(duration_s=1.0)
    timeline = schema.Timeline(tracks=[schema.Track(name="V1", clips=clips)])
    with pytest.raises(ValueError, match="overlaps by"):
        schema.validate(timeline)


def test_transition_must_fit_inside_both_clips():
    clips = [
        schema.Clip(source=schema.ClipSource(asset_id="a", in_s=0, out_s=4)),
        schema.Clip(source=schema.ClipSource(asset_id="a", in_s=10, out_s=14), record_start_s=3.5),
    ]
    clips[0].transition_out = schema.Transition(duration_s=3.5)  # overlap 0.5 != 3.5
    timeline = schema.Timeline(tracks=[schema.Track(name="V1", clips=clips)])
    with pytest.raises(ValueError, match="overlaps by"):
        schema.validate(timeline)

    # Matching overlap but the duration eats clip b entirely (b span 4, D=4).
    clips2 = [
        schema.Clip(source=schema.ClipSource(asset_id="a", in_s=0, out_s=8)),
        schema.Clip(source=schema.ClipSource(asset_id="a", in_s=10, out_s=14), record_start_s=4),
    ]
    clips2[0].transition_out = schema.Transition(duration_s=4.0)
    timeline2 = schema.Timeline(tracks=[schema.Track(name="V1", clips=clips2)])
    with pytest.raises(ValueError, match="does not fit"):
        schema.validate(timeline2)


def test_trailing_transition_is_rejected():
    timeline = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=0, out_s=4),
                        transition_out=schema.Transition(duration_s=1.0),
                    )
                ],
            )
        ]
    )
    with pytest.raises(ValueError, match="no following clip"):
        schema.validate(timeline)


def test_disabled_clips_do_not_participate_in_junctions():
    timeline = schema.Timeline(
        tracks=[
            schema.Track(
                name="V1",
                clips=[
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=0, out_s=4),
                        transition_out=schema.Transition(duration_s=1.0),
                    ),
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=10, out_s=14),
                        record_start_s=3,
                        enabled=False,
                    ),
                    schema.Clip(
                        source=schema.ClipSource(asset_id="a", in_s=20, out_s=24),
                        record_start_s=3,
                    ),
                ],
            )
        ]
    )
    schema.validate(timeline)  # junction lands on the next ENABLED clip
