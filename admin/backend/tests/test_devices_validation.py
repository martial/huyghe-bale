"""Device name validation — POST + PUT reject '/' and empty, and trim whitespace.

The bridge's /to/<name>/<rest> targeting relies on names being exact-match
friendly. Slashes in names would break path parsing; leading/trailing
whitespace would silently fail match.
"""

import json
import os

import pytest


@pytest.fixture
def client(tmp_path):
    tmp = str(tmp_path)
    os.makedirs(os.path.join(tmp, "devices"), exist_ok=True)

    from app import create_app
    app = create_app(data_dir=tmp, start_osc=False)

    from storage.json_store import JsonStore
    from api import devices as devices_mod
    devices_mod.store = JsonStore(tmp, "devices", "dev")
    with app.test_client() as c:
        yield c, devices_mod


def _post(client, payload):
    return client.post(
        "/api/v1/devices",
        data=json.dumps(payload),
        content_type="application/json",
    )


def _put(client, device_id, payload):
    return client.put(
        f"/api/v1/devices/{device_id}",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_post_trims_surrounding_whitespace(client):
    c, _ = client
    resp = _post(c, {"name": "  circadian  ", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "circadian"


def test_post_rejects_slash(client):
    c, _ = client
    resp = _post(c, {"name": "foo/bar", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"})
    assert resp.status_code == 400
    assert "/" in resp.get_json()["error"]


def test_post_rejects_empty(client):
    c, _ = client
    resp = _post(c, {"name": "   ", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"})
    assert resp.status_code == 400


def test_put_trims_and_persists(client):
    c, _ = client
    created = _post(c, {"name": "initial", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"}).get_json()
    resp = _put(c, created["id"], {"name": "  renamed  "})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "renamed"


def test_put_rejects_slash_in_name(client):
    c, _ = client
    created = _post(c, {"name": "ok", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"}).get_json()
    resp = _put(c, created["id"], {"name": "cold/vents"})
    assert resp.status_code == 400


# Note: PUT currently does a full-file replace (store.update vs store.patch),
# so a PUT without "name" wipes the record's name. The admin UI always sends
# the full form dict, so this is never triggered in practice. Preserving
# name across partial PUTs is a separate refactor (switch to store.patch)
# and out of scope for this change.
