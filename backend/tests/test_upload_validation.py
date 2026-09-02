import io

from conftest import upload_and_wait


def test_rejects_non_video_extension(client):
    res = client.post("/api/upload", files={"video": ("notes.txt", io.BytesIO(b"hello"))})
    assert res.status_code == 400
    assert ".txt" in res.json()["detail"]


def test_rejects_garbage_video_content(client):
    res = client.post(
        "/api/upload",
        files={
            "video": ("fake.mp4", io.BytesIO(b"this is definitely not a video" * 100)),
        },
    )
    assert res.status_code == 400
    assert "video" in res.json()["detail"].lower()


def test_rejects_oversized_upload(client, test_video, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1000)  # 1KB — test clip is bigger
    data = test_video.read_bytes()
    res = client.post("/api/upload", files={"video": ("big.mp4", io.BytesIO(data))})
    assert res.status_code == 413
    # Partial file must not linger in uploads.
    import os

    uploads = os.path.join(os.environ["CUTLASS_DATA"], "uploads")
    assert os.listdir(uploads) == []


def test_frames_manifest_and_serving(client, test_video):
    job = upload_and_wait(client, test_video)
    job_id = job["id"]

    frames = client.get(f"/api/jobs/{job_id}/frames").json()
    assert len(frames) >= 5
    assert all(set(f) == {"t", "file"} for f in frames)
    assert frames[0]["t"] == 0.0

    img = client.get(f"/api/jobs/{job_id}/frames/{frames[0]['file']}")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert len(img.content) > 1000


def test_frame_name_traversal_rejected(client, test_video):
    job = upload_and_wait(client, test_video)
    for bad in ("..%2Fsource.mp4", "frames.json", "frame_abc.jpg"):
        res = client.get(f"/api/jobs/{job['id']}/frames/{bad}")
        assert res.status_code in (400, 404), bad


def test_valid_upload_still_works(client, test_video):
    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")
