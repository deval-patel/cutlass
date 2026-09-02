"""SSE job/asset event endpoints, shared by both API versions.

The stream builder lives once; the legacy and v1 routers mount it at
their own paths.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..events import TERMINAL_STATUSES, get_broker
from ..repositories import assets as assets_repo

legacy_router = APIRouter(prefix="/api/jobs")
v1_router = APIRouter(prefix="/api/v1/assets")


@legacy_router.get("/{job_id}/events")
async def legacy_job_events(job_id: str) -> StreamingResponse:
    return await _events_response(job_id)


@v1_router.get("/{asset_id}/events")
async def asset_events(asset_id: str) -> StreamingResponse:
    return await _events_response(asset_id)


async def _events_response(asset_id: str) -> StreamingResponse:
    """Server-sent events for status/progress; closes on a terminal status."""
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")

    async def stream() -> AsyncIterator[str]:
        broker = get_broker()
        queue = broker.subscribe(asset_id)
        try:
            # Sync late subscribers with current state before live events.
            state = {"status": asset.status, "progress": asset.progress, "error": asset.error}
            yield _sse(state)
            if asset.status in TERMINAL_STATUSES:
                return
            while True:
                event = await queue.get()
                yield _sse(event.payload())
                if event.status in TERMINAL_STATUSES:
                    return
        finally:
            broker.unsubscribe(asset_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _sse(payload: dict[str, str | None]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
