"""WAL + busy_timeout must make concurrent repository writes safe.

FastAPI BackgroundTasks (and soon the worker pool) run in separate threads,
each opening its own connection — without WAL and a busy timeout this
reliably produces 'database is locked' under load.
"""

import threading

from app.repositories import jobs


def test_concurrent_writes_never_lock(client):
    jobs.create_job("conc1", "x.mp4")
    errors: list[Exception] = []

    def hammer() -> None:
        try:
            for i in range(25):
                jobs.set_progress("conc1", f"tick {i}")
                jobs.set_status("conc1", "analyzing")
        except Exception as exc:  # noqa: BLE001 — record any failure to assert after join
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    job = jobs.get_job("conc1")
    assert job is not None
    assert job.progress is not None and job.progress.startswith("tick")
