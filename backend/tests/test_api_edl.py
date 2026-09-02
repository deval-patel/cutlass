import time

from conftest import upload_and_wait, wait_for_status


def test_upload_to_ready(client, test_video):
    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")
    assert job["meta"]["duration_s"] == 10.0
    assert job["segments"], "dry-run EDL should contain at least one segment"


def test_update_segments_normalizes_and_invalidates_render(client, test_video):
    job = upload_and_wait(client, test_video)
    job_id = job["id"]

    # Edit while in ready state: overlapping/out-of-range input gets normalized.
    res = client.put(f"/api/jobs/{job_id}/segments", json=[
        {"start_s": 100.0, "end_s": 500.0, "reason": "clamp me", "confidence": 1.0},
        {"start_s": 2.0, "end_s": 4.0, "reason": "keep", "confidence": 0.9},
        {"start_s": 3.5, "end_s": 5.0, "reason": "overlap", "confidence": 0.9},
    ])
    assert res.status_code == 200, res.text
    updated = res.json()
    got = [(s["start_s"], s["end_s"]) for s in updated["segments"]]
    assert got == [(2.0, 5.0), (10.0, 10.0)] or got == [(2.0, 5.0)]
    # The clamped segment (100,10s video) is inverted → dropped.
    assert all(start < end for start, end in got)


def test_edit_lifecycle_with_render(client, test_video):
    job = upload_and_wait(client, test_video)
    job_id = job["id"]

    res = client.post(f"/api/jobs/{job_id}/render")
    assert res.status_code == 200
    job = wait_for_status(client, job_id, {"rendered", "failed"})
    assert job["status"] == "rendered", job.get("error")
    assert job["has_render"] is True

    # Editing after render invalidates the stale output.
    res = client.put(f"/api/jobs/{job_id}/segments", json=[
        {"start_s": 1.0, "end_s": 8.0, "reason": "manual", "confidence": 1.0},
    ])
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "ready"
    assert updated["has_render"] is False

    # The download endpoint reflects invalidation.
    assert client.get(f"/api/jobs/{job_id}/render").status_code == 404

    # Re-render uses the edited EDL.
    client.post(f"/api/jobs/{job_id}/render")
    job = wait_for_status(client, job_id, {"rendered", "failed"})
    assert job["status"] == "rendered", job.get("error")
    download = client.get(f"/api/jobs/{job_id}/render")
    assert download.status_code == 200
    assert len(download.content) > 10000


def test_edit_rejects_empty_result(client, test_video):
    job = upload_and_wait(client, test_video)
    job_id = job["id"]
    res = client.put(f"/api/jobs/{job_id}/segments", json=[
        {"start_s": 5.0, "end_s": 5.0, "reason": "empty", "confidence": 1.0},
    ])
    assert res.status_code == 422


def test_unknown_job_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.put("/api/jobs/nope/segments", json=[]).status_code == 404
