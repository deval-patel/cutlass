"""The /api/v1 surface: projects, assets, timeline documents."""

from conftest import wait_for_status


def _create_project(client, name="Japan trip"):
    res = client.post("/api/v1/projects", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()


def _upload_asset(client, project_id, video):
    with video.open("rb") as f:
        res = client.post(f"/api/v1/projects/{project_id}/assets", files={"video": ("day1.mp4", f)})
    assert res.status_code == 200, res.text
    return res.json()


def test_project_crud_and_listing(client):
    first = _create_project(client, "one")
    _create_project(client, "two")
    assert first["name"] == "one"

    listing = client.get("/api/v1/projects").json()
    assert [p["name"] for p in listing] == ["two", "one"]  # newest first
    assert all("assets" in p and "timeline_id" in p for p in listing)

    detail = client.get(f"/api/v1/projects/{first['id']}").json()
    assert detail["project"]["id"] == first["id"]
    assert detail["assets"] == []
    assert detail["timeline"] is None  # no assets yet: nothing to seed from


def test_upload_into_project_full_flow(client, test_video):
    project = _create_project(client)
    asset = _upload_asset(client, project["id"], test_video)
    wait_for_status(client, asset["id"], {"ready", "failed"})

    detail = client.get(f"/api/v1/projects/{project['id']}").json()
    assert detail["project"]["name"] == "Japan trip"
    assert len(detail["assets"]) == 1
    assert detail["assets"][0]["status"] == "ready"

    # The pipeline seeded the timeline from the draft EDL.
    timeline = detail["timeline"]
    assert timeline is not None and timeline["version"] == 1
    track = timeline["document"]["tracks"][0]
    assert track["name"] == "V1" and len(track["clips"]) >= 1


def test_timeline_get_put_versions_restore(client, test_video):
    project = _create_project(client)
    asset = _upload_asset(client, project["id"], test_video)
    wait_for_status(client, asset["id"], {"ready", "failed"})

    current = client.get(f"/api/v1/projects/{project['id']}/timeline").json()
    assert current["version"] == 1

    # Edit: disable every clip via PUT (validated server-side).
    document = current["document"]
    for track in document["tracks"]:
        for clip in track["clips"]:
            clip["enabled"] = False
    edited = client.put(f"/api/v1/projects/{project['id']}/timeline", json=document)
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2

    versions = client.get(f"/api/v1/projects/{project['id']}/timeline/versions").json()
    assert [v["version"] for v in versions] == [2, 1]

    restored = client.post(f"/api/v1/projects/{project['id']}/timeline/versions/1/restore")
    assert restored.status_code == 200
    body = restored.json()
    assert body["version"] == 3  # restore appends history
    assert all(c["enabled"] for t in body["document"]["tracks"] for c in t["clips"])


def test_timeline_rejects_invalid_document(client, test_video):
    project = _create_project(client)
    _upload_asset(client, project["id"], test_video)
    wait_for_status(client, _first_asset_id(client, project["id"]), {"ready", "failed"})

    current = client.get(f"/api/v1/projects/{project['id']}/timeline").json()
    doc = current["document"]
    doc["tracks"][0]["clips"].append(
        {  # overlapping clip at the same record time
            "source": {
                "asset_id": doc["tracks"][0]["clips"][0]["source"]["asset_id"],
                "in_s": 99,
                "out_s": 100,
            },
            "record_start_s": 0,
        }
    )
    res = client.put(f"/api/v1/projects/{project['id']}/timeline", json=doc)
    assert res.status_code == 422
    assert "overlap" in res.json()["detail"]


def test_render_via_v1(client, test_video):
    project = _create_project(client)
    asset = _upload_asset(client, project["id"], test_video)
    wait_for_status(client, asset["id"], {"ready", "failed"})

    assert client.post(f"/api/v1/assets/{asset['id']}/render").json() == {"status": "rendering"}
    final = wait_for_status(client, asset["id"], {"rendered", "failed"})
    assert final["status"] == "rendered", final.get("error")

    download = client.get(f"/api/v1/assets/{asset['id']}/render")
    assert download.status_code == 200 and len(download.content) > 10000


def test_unknown_ids_404(client):
    assert client.get("/api/v1/projects/nope").status_code == 404
    assert client.get("/api/v1/assets/nope").status_code == 404
    assert client.get("/api/v1/projects/nope/timeline").status_code == 404


def _first_asset_id(client, project_id):
    detail = client.get(f"/api/v1/projects/{project_id}").json()
    return detail["assets"][0]["id"]
