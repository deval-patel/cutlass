"""Asset analysis state: frame notes, progress round-trip, migration idempotency."""

from conftest import upload_and_wait


def test_ready_asset_has_frame_notes(client, test_video):
    asset = upload_and_wait(client, test_video)
    assert asset["status"] == "ready", asset.get("error")

    notes = asset["frame_notes"]
    assert len(notes) >= 5  # 10s video at 1s sampling
    assert all(
        n["label"] in ("core", "filler", "dead_air", "intro_outro", "repetition", "other")
        for n in notes
    )
    # Every note must land inside the video's timeline.
    assert all(0 <= n["timestamp_s"] <= asset["meta"]["duration_s"] + 1e-6 for n in notes)
    # Progress is cleared once terminal.
    assert asset["progress"] is None


def test_progress_roundtrip_and_migration(client):
    from app.db import migrations
    from app.repositories import assets as assets_repo
    from app.repositories import projects as projects_repo

    # Migrations must be idempotent and tolerate pre-existing schemas.
    migrations.ensure_current()
    migrations.ensure_current()

    projects_repo.create_project("proj-p1", "x.mp4")
    assets_repo.create_asset("prog1", "proj-p1", "x.mp4")
    assets_repo.set_progress("prog1", "analyzing chunk 2/5")
    asset = assets_repo.get_asset("prog1")
    assert asset is not None and asset.progress == "analyzing chunk 2/5"

    assets_repo.set_notes(
        "prog1",
        [
            {"timestamp_s": 1.0, "description": "hello", "label": "core"},
        ],
    )
    asset = assets_repo.get_asset("prog1")
    assert asset is not None and asset.frame_notes[0].description == "hello"

    assets_repo.set_progress("prog1", None)
    refreshed = assets_repo.get_asset("prog1")
    assert refreshed is not None and refreshed.progress is None
