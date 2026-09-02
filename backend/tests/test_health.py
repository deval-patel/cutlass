"""Liveness endpoint contract — used by the Docker HEALTHCHECK."""

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
