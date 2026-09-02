from conftest import upload_and_wait


def test_job_list_after_uploads(client, test_video):
    first = upload_and_wait(client, test_video)
    second = upload_and_wait(client, test_video)

    res = client.get("/api/jobs")
    assert res.status_code == 200
    jobs = res.json()
    ids = [j["id"] for j in jobs]
    assert first["id"] in ids and second["id"] in ids

    # Summaries carry the fields the UI list needs.
    entry = next(j for j in jobs if j["id"] == second["id"])
    assert entry["filename"] == "test.mp4"
    assert entry["status"] == "ready"
    assert entry["duration_s"] == 10.0
    assert entry["segments"] >= 1
    assert entry["created_at"]

    # Newest first.
    assert jobs[0]["id"] == second["id"]


def test_job_list_empty(client):
    res = client.get("/api/jobs")
    assert res.status_code == 200
    assert res.json() == []
