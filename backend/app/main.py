import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import migrations
from .events import get_broker
from .routers import api_v1, events, videos
from .services.queue import get_queue

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start the worker queue (recovering work stranded by a crash) and stop
    it cleanly on shutdown, letting in-flight tasks finish."""
    get_broker().set_loop(asyncio.get_running_loop())
    job_queue = get_queue()
    job_queue.recover_pending()
    job_queue.start()
    yield
    job_queue.stop()
    get_broker().set_loop(None)


app = FastAPI(title="Cutlass", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
migrations.ensure_current()
app.include_router(videos.router)
app.include_router(events.legacy_router)
app.include_router(api_v1.router)
app.include_router(events.v1_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe (used by the Docker HEALTHCHECK and uptime monitors)."""
    return {"status": "ok"}


# Serve the built frontend when it exists (dev uses Vite on :5173).
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_dist / "index.html")
