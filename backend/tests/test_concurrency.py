"""WAL + busy_timeout must make concurrent repository writes safe.

FastAPI BackgroundTasks (and soon the worker pool) run in separate threads,
each opening its own connection — without WAL and a busy timeout this
reliably produces 'database is locked' under load.
"""

import threading

from app.repositories import assets as assets_repo
from app.repositories import projects as projects_repo


def test_concurrent_writes_never_lock(client):
    projects_repo.create_project("proj-conc", "x.mp4")
    assets_repo.create_asset("conc1", "proj-conc", "x.mp4")
    errors: list[Exception] = []

    def hammer() -> None:
        try:
            for i in range(25):
                assets_repo.set_progress("conc1", f"tick {i}")
                assets_repo.set_status("conc1", "analyzing")
        except Exception as exc:  # noqa: BLE001 — record any failure to assert after join
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    asset = assets_repo.get_asset("conc1")
    assert asset is not None
    assert asset.progress is not None and asset.progress.startswith("tick")
