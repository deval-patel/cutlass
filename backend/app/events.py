"""In-process pub/sub bridging worker threads to SSE subscribers.

The job queue runs in plain threads; SSE endpoints run on the event loop.
Publishers call ``publish`` from any thread — the broker forwards to
subscriber queues via ``loop.call_soon_threadsafe``. Delivery is
best-effort: publishing must never break the database write that owns it,
and events are dropped when nobody is listening (the SSE endpoint always
sends current state first, so late subscribers sync immediately).
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"ready", "rendered", "failed"}


class JobEvent:
    __slots__ = ("error", "job_id", "progress", "status")

    def __init__(
        self,
        job_id: str,
        status: str | None = None,
        progress: str | None = None,
        error: str | None = None,
    ) -> None:
        self.job_id = job_id
        self.status = status
        self.progress = progress
        self.error = error

    def payload(self) -> dict[str, str | None]:
        return {"status": self.status, "progress": self.progress, "error": self.error}


class Broker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[JobEvent]]] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def subscribe(self, job_id: str) -> asyncio.Queue[JobEvent]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[JobEvent]) -> None:
        with self._lock:
            listeners = self._subscribers.get(job_id)
            if listeners is not None:
                listeners.discard(queue)
                if not listeners:
                    self._subscribers.pop(job_id, None)

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            listeners = list(self._subscribers.get(event.job_id, ()))
        if not listeners or self._loop is None:
            return
        for queue in listeners:
            try:
                self._loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # Loop shutting down; delivery is best-effort by contract.
                logger.debug("dropping event for %s during shutdown", event.job_id)


_broker: Broker | None = None


def get_broker() -> Broker:
    global _broker
    if _broker is None:
        _broker = Broker()
    return _broker
