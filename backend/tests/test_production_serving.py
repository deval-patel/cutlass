"""The Docker container serves the built frontend from FastAPI — this exercises
that exact path (skipped when frontend/dist hasn't been built)."""

from pathlib import Path

import pytest
from conftest import upload_and_wait, wait_for_status

DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

pytestmark = pytest.mark.skipif(not DIST.exists(), reason="frontend/dist not built")


def test_index_and_assets_served(client):
    index = client.get("/")
    assert index.status_code == 200
    assert 'id="root"' in index.text
    assert "text/html" in index.headers["content-type"]


def test_deep_links_serve_the_app_shell(client):
    """The frontend routes client-side; /p/{id} must return index.html."""
    deep = client.get("/p/some-project-id")
    assert deep.status_code == 200
    assert 'id="root"' in deep.text
    # API paths are never swallowed by the SPA fallback.
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/v1/projects/nope").status_code == 404


def test_bundled_asset_reachable(client):
    index = client.get("/").text
    import re

    match = re.search(r'src="/(assets/[^"]+\.js)"', index)
    assert match, "no script bundle referenced in index.html"
    js = client.get("/" + match.group(1))
    assert js.status_code == 200
    assert len(js.content) > 10000


def test_full_pipeline_same_origin(client, test_video):
    """Upload → analysis → render → download, exactly as the container runs it."""
    job = upload_and_wait(client, test_video)
    assert job["status"] == "ready", job.get("error")
    assert job["transcript"], "transcription should run in the pipeline"
    assert client.post(f"/api/jobs/{job['id']}/render").status_code == 200
    job = wait_for_status(client, job["id"], {"rendered", "failed"})
    assert job["status"] == "rendered", job.get("error")
    download = client.get(f"/api/jobs/{job['id']}/render")
    assert download.status_code == 200 and len(download.content) > 10000
