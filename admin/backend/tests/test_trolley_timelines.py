"""Smoke tests for the trolley timelines CRUD blueprint."""

import json
import os
import tempfile

import pytest


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "trolley_timelines"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "devices"), exist_ok=True)

    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp)

    # Re-import the blueprints with the new DATA_DIR
    from app import create_app
    app = create_app(data_dir=tmp, start_osc=False)
    with app.test_client() as c:
        yield c


def test_create_and_list(client):
    resp = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({"name": "Rail run", "duration": 12}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    tl = resp.get_json()
    assert tl["name"] == "Rail run"
    assert tl["duration"] == 12
    assert tl["lane"]["label"] == "Position"

    resp = client.get("/api/v1/trolley-timelines")
    assert resp.status_code == 200
    rows = resp.get_json()
    assert len(rows) == 1
    assert rows[0]["id"] == tl["id"]
    assert rows[0]["points"] == 0


def test_update_and_fetch(client):
    tl = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({"name": "X", "duration": 10}),
        content_type="application/json",
    ).get_json()

    updated = {
        **tl,
        "name": "Renamed",
        "lane": {
            "label": "Position",
            "points": [
                {"id": "p1", "time": 0, "value": 0, "curve_type": "linear", "bezier_handles": None},
                {"id": "p2", "time": 5, "value": 0.5, "curve_type": "linear", "bezier_handles": None},
            ],
        },
    }
    resp = client.put(
        f"/api/v1/trolley-timelines/{tl['id']}",
        data=json.dumps(updated),
        content_type="application/json",
    )
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/trolley-timelines/{tl['id']}")
    body = resp.get_json()
    assert body["name"] == "Renamed"
    assert len(body["lane"]["points"]) == 2


def test_duplicate_and_delete(client):
    tl = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({"name": "A", "duration": 10}),
        content_type="application/json",
    ).get_json()

    dup = client.post(f"/api/v1/trolley-timelines/{tl['id']}/duplicate").get_json()
    assert dup["id"] != tl["id"]
    assert dup["name"].endswith("(copy)")

    assert client.delete(f"/api/v1/trolley-timelines/{tl['id']}").status_code == 200
    assert client.get(f"/api/v1/trolley-timelines/{tl['id']}").status_code == 404
