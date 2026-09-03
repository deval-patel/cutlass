"""Durable in-process job queue (Plan 1).

FastAPI BackgroundTasks die with the process and give no bound on how many
ffmpeg/model tasks run at once. This queue is a small fixed thread pool
pulling from an in-memory queue, with crash recovery: on startup every job
left in a non-terminal state is re-enqueued, so a killed server finishes
the work when it comes back. Tasks must therefore be idempotent — the
analysis pipeline and the renderer both overwrite their outputs.
"""

import logging
import queue as stdqueue
import threading
from collections.abc import Callable, Mapping
from typing import Literal

from .. import config
from ..repositories import assets as assets_repo

logger = logging.getLogger(__name__)

TaskKind = Literal["analyze", "redraft", "redraft-project", "render"]
Task = tuple[TaskKind, str] | None  # None is the shutdown sentinel

# A job in one of these states has work outstanding; map it to the task
# that resumes it. Everything else is terminal.
_RECOVERY: dict[str, TaskKind] = {
    "uploaded": "analyze",
    "sampling": "analyze",
    "analyzing": "analyze",
    "redrafting": "redraft",
    "rendering": "render",
}


def _default_handlers() -> Mapping[str, Callable[[str], None]]:
    from . import analyzer

    return {
        "analyze": analyzer.run_pipeline,
        "redraft": analyzer.run_redraft,
        "redraft-project": analyzer.run_project_redraft,
        "render": analyzer.run_render,
    }


class JobQueue:
    def __init__(
        self,
        workers: int = 2,
        handlers: Mapping[str, Callable[[str], None]] | None = None,
    ) -> None:
        self._tasks: stdqueue.Queue[Task] = stdqueue.Queue()
        self._handlers = handlers if handlers is not None else _default_handlers()
        self._shutdown = threading.Event()
        self._started = False
        self._worker_count = max(1, workers)
        self._workers: list[threading.Thread] = []

    def start(self) -> None:
        if self._started:
            return
        self._shutdown.clear()
        # Threads cannot be restarted once exited, so spawn fresh ones every
        # start (the queue is stopped/started with the app lifespan).
        self._workers = [
            threading.Thread(target=self._run, name=f"cutlass-worker-{i}", daemon=True)
            for i in range(self._worker_count)
        ]
        for worker in self._workers:
            worker.start()
        self._started = True

    def stop(self, timeout_s: float = 15.0) -> None:
        """Finish in-flight tasks, wake idle workers, join all threads."""
        if not self._started:
            return
        self._shutdown.set()
        for _ in self._workers:
            self._tasks.put_nowait(None)
        for worker in self._workers:
            worker.join(timeout_s)
        self._started = False

    def enqueue(self, kind: TaskKind, job_id: str) -> None:
        if kind not in self._handlers:
            raise ValueError(f"unknown task kind {kind!r}")
        logger.info("queued %s for job %s", kind, job_id)
        self._tasks.put_nowait((kind, job_id))

    def recover_pending(self) -> list[tuple[TaskKind, str]]:
        """Re-enqueue work stranded by a crash/restart. Returns what was queued."""
        recovered: list[tuple[TaskKind, str]] = []
        for asset in assets_repo.list_assets():
            kind = _RECOVERY.get(asset.status)
            if kind is not None:
                logger.info("recovering asset %s (%s) as %s", asset.id, asset.status, kind)
                self.enqueue(kind, asset.id)
                recovered.append((kind, asset.id))
        return recovered

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            try:
                if task is None:
                    return
                kind, job_id = task
                self._handlers[kind](job_id)
            except Exception:
                logger.exception("task failed: %s", task)
            finally:
                self._tasks.task_done()


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    """Process-wide queue; the app lifespan starts/stops it."""
    global _queue
    if _queue is None:
        _queue = JobQueue(workers=config.QUEUE_WORKERS)
    return _queue
