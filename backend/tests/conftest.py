import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Configure the app environment before any app module is imported. Real env
# vars win over the developer's .env file, so pin everything the suite depends
# on — otherwise a local .env (e.g. TRANSCRIBE_ENABLED=0) breaks tests.
_TMP = tempfile.mkdtemp(prefix="cutlass-test-")
os.environ["DRY_RUN"] = "1"
os.environ["CUTLASS_DATA"] = _TMP
os.environ["TRANSCRIBE_ENABLED"] = "1"

from fastapi.testclient import TestClient

from app.main import app

FFMPEG_MISSING = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # pytestmark in conftest.py does not propagate to test modules, so skip
    # via the collection hook instead: without ffmpeg the pipeline tests
    # can't run and should skip, not error out at fixture setup.
    if FFMPEG_MISSING:
        skip = pytest.mark.skip(reason="ffmpeg/ffprobe not on PATH")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_video() -> Path:
    """Generate a 10s test clip once per session."""
    path = Path(_TMP) / "test_video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=10:size=640x360:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture()
def client():
    from app import storage

    storage_dir = Path(os.environ["CUTLASS_DATA"]) / "uploads"
    # Fresh uploads + jobs per test keeps tests isolated.
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    with storage._connect() as conn:
        conn.execute("DELETE FROM jobs")
    with TestClient(app) as c:
        yield c


def wait_for_status(client: TestClient, job_id: str, statuses: set[str], timeout_s: float = 60):
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {statuses}; last: {job}")


def upload_and_wait(client: TestClient, video: Path) -> dict:
    with video.open("rb") as f:
        res = client.post("/api/upload", files={"video": ("test.mp4", f)})
    assert res.status_code == 200, res.text
    return wait_for_status(client, res.json()["id"], {"ready", "failed"})
