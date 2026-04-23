"""Tests for /api/v1/protocol-test endpoints."""

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

    vents = devices_mod.store.create(
        {
            "name": "v1",
            "ip_address": "10.0.0.1",
            "osc_port": 9000,
            "type": "vents",
        }
    )
    trolley = devices_mod.store.create(
        {
            "name": "t1",
            "ip_address": "10.0.0.2",
            "osc_port": 9000,
            "type": "trolley",
        }
    )

    with app.test_client() as c:
        yield c, vents["id"], trolley["id"], devices_mod


def test_osc_wrong_prefix_for_device_type(client):
    c, vents_id, trolley_id, _ = client
    r = c.post(
        "/api/v1/protocol-test/osc",
        data=json.dumps(
            {"device_id": vents_id, "address": "/trolley/stop", "values": []},
        ),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_osc_ok(monkeypatch, client):
    c, vents_id, _, _ = client

    calls = []

    def fake_send_values(ip, port, addr, vals):
        calls.append((ip, port, addr, vals))

    monkeypatch.setattr(
        "api.protocol_test._osc.send_values",
        fake_send_values,
    )

    r = c.post(
        "/api/v1/protocol-test/osc",
        data=json.dumps(
            {"device_id": vents_id, "address": "/vents/fan/1", "values": [0.5]},
        ),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert calls == [("10.0.0.1", 9000, "/vents/fan/1", [0.5])]


def test_http_disallowed_path(client):
    c, vents_id, _, _ = client
    r = c.post(
        "/api/v1/protocol-test/http",
        data=json.dumps(
            {"device_id": vents_id, "method": "GET", "path": "/etc/passwd"},
        ),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_bridge_disabled_skips_listen_but_returns_503(client):
    c, vents_id, _, _ = client

    from api import settings as settings_mod

    settings_mod._write({**settings_mod._read(), "bridge_enabled": False})

    r = c.post(
        "/api/v1/protocol-test/bridge",
        data=json.dumps({"address": "/vents/fan/1", "values": [0.5]}),
        content_type="application/json",
    )
    assert r.status_code == 503


def test_bridge_requires_inner_or_address(client):
    from api import settings as settings_mod

    settings_mod._write({**settings_mod._read(), "bridge_enabled": True})

    c, _, _, _ = client
    r = c.post(
        "/api/v1/protocol-test/bridge",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert r.status_code == 400
