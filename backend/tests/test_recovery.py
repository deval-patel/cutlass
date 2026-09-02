"""Crash recovery, end to end: a job stranded mid-analysis is finished on restart.

Simulates 'kill -9 during analysis' by leaving an asset in a non-terminal
state with its source on disk, then boots the app — the lifespan's
recover_pending() must re-enqueue the work and drive it to ready.
"""

from pathlib import Path

from conftest import wait_for_status
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import assets as assets_repo
from app.repositories import projects as projects_repo


def test_stranded_analysis_resumes_on_restart(client, test_video):
    # Upload completes and analysis finishes under normal operation; reset the
    # asset to mid-flight to simulate the crash, with artifacts on disk.
    from conftest import upload_and_wait

    asset = upload_and_wait(client, test_video)
    asset_id = asset["id"]
    assets_repo.set_status(asset_id, "analyzing")
    assets_repo.set_progress(asset_id, "analyzing chunk 1/2")
    assert Path(test_video).exists()

    # 'Restart': a fresh app lifecycle runs recovery + a fresh worker pool.
    with TestClient(app) as restarted:
        job = wait_for_status(restarted, asset_id, {"ready", "failed"})
        assert job["status"] == "ready", job.get("error")


def test_restart_with_clean_state_is_a_noop(client):
    with TestClient(app) as restarted:
        assert restarted.get("/api/health").json() == {"status": "ok"}


def test_recovery_ignores_assets_without_a_timeline_seedable(client):
    """A stranded multi-asset-less empty project must not crash startup."""
    projects_repo.create_project("proj-empty", "empty.mp4")
    with TestClient(app) as restarted:
        assert restarted.get("/api/v1/projects/proj-empty").status_code == 200
