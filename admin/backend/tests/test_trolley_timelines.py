"""Smoke tests for the trolley timelines (event-based) CRUD blueprint."""

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
    assert tl["events"] == []
    assert "lane" not in tl

    resp = client.get("/api/v1/trolley-timelines")
    rows = resp.get_json()
    assert rows[0]["events"] == 0


def test_update_events_sorted_and_normalized(client):
    tl = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({"name": "X", "duration": 20}),
        content_type="application/json",
    ).get_json()

    payload = {
        **tl,
        "events": [
            {"id": "e3", "time": 10, "command": "stop"},
            {"id": "e1", "time": 0, "command": "enable", "value": 1},
            {"id": "e2", "time": 2.5, "command": "position", "value": 0.5},
            # Invalid — dropped silently
            {"id": "bad", "time": 3, "command": "teleport"},
            # Missing value for a value-command — dropped
            {"id": "bad2", "time": 4, "command": "speed"},
        ],
    }
    resp = client.put(
        f"/api/v1/trolley-timelines/{tl['id']}",
        data=json.dumps(payload),
        content_type="application/json",
    ).get_json()
    # Only valid events survive, sorted by time
    times = [e["time"] for e in resp["events"]]
    assert times == [0.0, 2.5, 10.0]
    assert [e["command"] for e in resp["events"]] == ["enable", "position", "stop"]
    # enable.value coerced to float on storage
    assert resp["events"][0]["value"] == 1.0


def test_migration_from_legacy_lane(client):
    """Timelines stored under the old lane schema are translated to events on read."""
    # Use the blueprint's own store (bound at import time) so GET finds the record.
    from api import trolley_timelines as mod
    legacy = mod.store.create({
        "name": "Legacy",
        "duration": 30,
        "lane": {
            "label": "Position",
            "points": [
                {"id": "p1", "time": 0, "value": 0, "curve_type": "linear"},
                {"id": "p2", "time": 15, "value": 0.75, "curve_type": "linear"},
            ],
        },
    })
    resp = client.get(f"/api/v1/trolley-timelines/{legacy['id']}")
    body = resp.get_json()
    assert "lane" not in body
    assert [e["command"] for e in body["events"]] == ["position", "position"]
    assert [e["value"] for e in body["events"]] == [0.0, 0.75]


def test_duplicate_preserves_events(client):
    tl = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({
            "name": "A",
            "duration": 10,
            "events": [{"id": "e1", "time": 0, "command": "home"}],
        }),
        content_type="application/json",
    ).get_json()

    dup = client.post(f"/api/v1/trolley-timelines/{tl['id']}/duplicate").get_json()
    assert dup["id"] != tl["id"]
    assert dup["name"].endswith("(copy)")
    assert len(dup["events"]) == 1
    assert dup["events"][0]["command"] == "home"


def test_delete(client):
    tl = client.post(
        "/api/v1/trolley-timelines",
        data=json.dumps({"name": "D", "duration": 5}),
        content_type="application/json",
    ).get_json()
    assert client.delete(f"/api/v1/trolley-timelines/{tl['id']}").status_code == 200
    assert client.get(f"/api/v1/trolley-timelines/{tl['id']}").status_code == 404
