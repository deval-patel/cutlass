import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import migrations
from .routers import videos

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Cutlass")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
migrations.ensure_current()
app.include_router(videos.router)


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
