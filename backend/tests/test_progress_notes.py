from conftest import upload_and_wait


def test_ready_job_has_frame_notes(client, test_video):
    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")

    notes = job["frame_notes"]
    assert len(notes) >= 5  # 10s video at 1s sampling
    assert all(
        n["label"] in ("core", "filler", "dead_air", "intro_outro", "repetition", "other")
        for n in notes
    )
    # Every note must land inside the video's timeline.
    assert all(0 <= n["timestamp_s"] <= job["meta"]["duration_s"] + 1e-6 for n in notes)
    # Progress is cleared once terminal.
    assert job["progress"] is None


def test_progress_roundtrip_and_migration(client):
    from app import storage

    # init_db must be idempotent and tolerate pre-existing schemas.
    storage.init_db()
    storage.init_db()

    storage.create_job("prog1", "x.mp4")
    storage.set_progress("prog1", "analyzing chunk 2/5")
    job = storage.get_job("prog1")
    assert job.progress == "analyzing chunk 2/5"

    storage.set_notes(
        "prog1",
        [
            {"timestamp_s": 1.0, "description": "hello", "label": "core"},
        ],
    )
    job = storage.get_job("prog1")
    assert job.frame_notes[0].description == "hello"

    storage.set_progress("prog1", None)
    assert storage.get_job("prog1").progress is None
