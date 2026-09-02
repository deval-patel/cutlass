"""Storage lifecycle: deleting projects removes rows AND artifacts;
transcription scratch audio never outlives the pipeline."""

import os
from pathlib import Path

from conftest import upload_and_wait


def test_delete_project_removes_rows_and_artifacts(client, test_video):
    asset = upload_and_wait(client, test_video)
    asset_id = asset["id"]
    uploads = Path(os.environ["CUTLASS_DATA"]) / "uploads"
    assert (uploads / asset_id / "source.mp4").exists()
    assert (uploads / asset_id / "frames").exists()

    from app.repositories import assets as assets_repo

    project_id = assets_repo.get_asset(asset_id).project_id

    res = client.delete(f"/api/v1/projects/{project_id}")
    assert res.status_code == 200 and res.json() == {"deleted": True}

    assert assets_repo.get_asset(asset_id) is None
    assert not (uploads / asset_id).exists()
    assert client.get(f"/api/jobs/{asset_id}").status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 404


def test_transcription_scratch_audio_is_cleaned_up(client, test_video):
    asset = upload_and_wait(client, test_video)
    assert asset["status"] == "ready", asset.get("error")

    uploads = Path(os.environ["CUTLASS_DATA"]) / "uploads"
    audio_dir = uploads / asset["id"] / "audio"
    assert not audio_dir.exists(), "chunk WAVs are scratch; the transcript is what persists"
    # The transcript itself survived the cleanup.
    assert len(asset["transcript"]) >= 1
