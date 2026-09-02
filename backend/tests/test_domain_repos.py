"""Project/Asset/Timeline repositories: CRUD, versioning, cascade deletes."""

import pytest

from app.models import Segment
from app.repositories import assets as assets_repo
from app.repositories import projects as projects_repo
from app.repositories import timelines as timelines_repo
from app.timelines import schema


def _project(name: str = "trip") -> str:
    project_id = f"proj-{name}"
    projects_repo.create_project(project_id, name)
    return project_id


def test_project_asset_roundtrip(client):
    project_id = _project()
    assets_repo.create_asset("asset-1", project_id, "day1.mp4")

    asset = assets_repo.get_asset("asset-1")
    assert asset is not None
    assert asset.project_id == project_id
    assert asset.status == "uploaded"
    assert assets_repo.list_assets(project_id)[0].id == "asset-1"

    assets_repo.set_segments(
        "asset-1", [Segment(start_s=0.0, end_s=3.0, reason="r", confidence=1.0)]
    )
    assert assets_repo.get_asset("asset-1").segments[0].end_s == 3.0


def test_timeline_versions_and_restore(client):
    project_id = _project()
    timeline = schema.from_segments(
        [Segment(start_s=0.0, end_s=3.0, reason="v1", confidence=1.0)], asset_id="asset-1"
    )
    _timeline_id, v1 = timelines_repo.save_timeline(project_id, timeline, label="draft")
    assert v1 == 1

    timeline.tracks[0].clips[0].reason = "tightened"
    _, v2 = timelines_repo.save_timeline(project_id, timeline, label="edit")
    assert v2 == 2

    stored = timelines_repo.get_timeline(project_id)
    assert stored is not None and stored[1] == 2
    assert stored[2].tracks[0].clips[0].reason == "tightened"

    versions = timelines_repo.list_versions(project_id)
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["label"] == "draft"

    restored = timelines_repo.restore_version(project_id, 1)
    assert restored is not None
    new_version, document = restored
    assert new_version == 3  # restore appends history, never rewrites it
    assert document.tracks[0].clips[0].reason == "v1"


def test_invalid_timeline_never_reaches_storage(client):
    project_id = _project()
    timeline = schema.from_segments(
        [Segment(start_s=0.0, end_s=3.0, reason="r", confidence=1.0)], asset_id="asset-1"
    )
    timeline.tracks[0].clips.append(
        schema.Clip(  # overlaps the first clip at record time
            source=schema.ClipSource(asset_id="asset-1", in_s=10, out_s=20),
            record_start_s=1,
        )
    )
    with pytest.raises(ValueError, match="overlap"):
        timelines_repo.save_timeline(project_id, timeline)
    assert timelines_repo.get_timeline(project_id) is None


def test_delete_project_cascades(client):
    project_id = _project()
    assets_repo.create_asset("asset-2", project_id, "day2.mp4")
    timelines_repo.save_timeline(project_id, schema.from_segments([], asset_id="asset-2"))

    assert projects_repo.delete_project(project_id) is True
    assert assets_repo.get_asset("asset-2") is None
    assert timelines_repo.get_timeline(project_id) is None
    assert projects_repo.delete_project(project_id) is False


def test_project_summaries_aggregate(client):
    first = _project("one")
    _project("two")  # newer, so it lists first
    assets_repo.create_asset("a-one", first, "day1.mp4")

    summaries = projects_repo.list_projects()
    assert [s.name for s in summaries] == ["two", "one"]
    entry = next(s for s in summaries if s.name == "one")
    assert entry.assets == 1
    assert entry.timeline_id is None
