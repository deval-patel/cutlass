"""SSE events endpoint: syncs current state, streams live updates, closes on terminal.

Note: starlette's TestClient drains a whole response before ``send()``
returns, so an unbounded SSE stream can't be consumed incrementally over
HTTP in tests (a real ASGI server streams chunk by chunk). The terminal-
state test exercises the real HTTP path; the live-update test drives the
endpoint's body iterator on its own event loop instead.
"""

import asyncio
import json
import threading
import time

from app.events import get_broker
from app.repositories import assets as assets_repo
from app.repositories import projects as projects_repo
from app.routers.videos import job_events


def _parse_events(raw: str) -> list[dict[str, str | None]]:
    lines = [ln for ln in raw.splitlines() if ln.startswith("data: ")]
    return [json.loads(ln[len("data: ") :]) for ln in lines]


def _seed_asset(asset_id: str, status: str) -> None:
    projects_repo.create_project(f"proj-{asset_id}", "x.mp4")
    assets_repo.create_asset(asset_id, f"proj-{asset_id}", "x.mp4")
    assets_repo.set_status(asset_id, status)


def test_events_sync_and_close_for_terminal_job(client):
    _seed_asset("evt-ready", "ready")

    with client.stream("GET", "/api/jobs/evt-ready/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())

    events = _parse_events(raw)
    assert events == [{"status": "ready", "progress": None, "error": None}]


def test_events_stream_live_updates_until_terminal(client):
    _seed_asset("evt-live", "analyzing")

    async def scenario() -> str:
        # Worker threads publish through the broker; give it this loop so
        # publishes reach the stream (the app lifespan does this in prod).
        broker = get_broker()
        broker.set_loop(asyncio.get_running_loop())
        try:
            response = await job_events("evt-live")
            collected: list[str] = []

            def drive() -> None:
                # The stream subscribes before its first yield; publish after
                # a short delay so events land after subscription.
                time.sleep(0.3)
                assets_repo.set_progress("evt-live", "analyzing chunk 1/2")
                assets_repo.set_status("evt-live", "ready")

            thread = threading.Thread(target=drive)
            thread.start()
            async for chunk in response.body_iterator:
                collected.append(chunk)
            thread.join(timeout=5)
            return "".join(collected)
        finally:
            broker.set_loop(None)

    events = _parse_events(asyncio.run(scenario()))
    statuses = [e["status"] for e in events]
    assert statuses[0] == "analyzing"  # initial sync with current state
    assert "ready" in statuses  # terminal event ends the stream
    assert "analyzing chunk 1/2" in [e["progress"] for e in events]


def test_events_unknown_job_404(client):
    assert client.get("/api/jobs/nope/events").status_code == 404
