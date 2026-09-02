"""Job-queue contract: execution, bounded workers, and crash recovery."""

import threading
import time

import pytest

from app.repositories import assets as assets_repo
from app.repositories import projects as projects_repo
from app.services.queue import JobQueue


def _recording_queue() -> tuple[JobQueue, list[tuple[str, str]], threading.Event]:
    done = threading.Event()
    executed: list[tuple[str, str]] = []
    lock = threading.Lock()

    def handler(job_id: str) -> None:
        with lock:
            executed.append(("analyze", job_id))
        done.set()

    queue = JobQueue(workers=1, handlers={"analyze": handler})
    return queue, executed, done


def test_queue_executes_enqueued_task():
    queue, executed, done = _recording_queue()
    queue.start()
    try:
        queue.enqueue("analyze", "job1")
        assert done.wait(timeout=5), "task never ran"
    finally:
        queue.stop()
    assert executed == [("analyze", "job1")]


def test_enqueue_rejects_unknown_kind():
    queue = JobQueue(workers=1, handlers={"analyze": lambda _job_id: None})
    try:
        queue.enqueue("analyze", "job1")  # fine
        with pytest.raises(ValueError):
            queue.enqueue("transcode", "job1")  # type: ignore[arg-type]
    finally:
        queue.stop()


def test_recovery_reenqueues_only_nonterminal_work(client):
    # One asset per status: only non-terminal ones have work outstanding.
    for status in ("uploaded", "sampling", "analyzing", "rendering", "ready", "rendered", "failed"):
        projects_repo.create_project(f"proj-rec-{status}", f"{status}.mp4")
        assets_repo.create_asset(f"rec-{status}", f"proj-rec-{status}", f"{status}.mp4")
        assets_repo.set_status(f"rec-{status}", status)

    queue = JobQueue(workers=1, handlers={"analyze": lambda _j: None, "render": lambda _j: None})
    recovered = queue.recover_pending()

    kinds = {job_id: kind for kind, job_id in recovered}
    assert kinds == {
        "rec-uploaded": "analyze",
        "rec-sampling": "analyze",
        "rec-analyzing": "analyze",
        "rec-rendering": "render",
    }


def test_stop_finishes_inflight_task():
    started = threading.Event()
    finished = threading.Event()

    def slow_handler(_job_id: str) -> None:
        started.set()
        time.sleep(0.2)
        finished.set()

    queue = JobQueue(workers=1, handlers={"analyze": slow_handler})
    queue.start()
    queue.enqueue("analyze", "slow")
    assert started.wait(timeout=5)
    queue.stop()  # must wait for the in-flight task, not drop it
    assert finished.is_set()
