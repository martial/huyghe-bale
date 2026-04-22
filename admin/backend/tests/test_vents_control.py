"""Tests for the vents-control blueprint — raw OSC commands + live status readout."""

import json
import os
from unittest.mock import patch

import pytest


@pytest.fixture
def ctx(tmp_path):
    tmp = str(tmp_path)
    for sub in ("devices",):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)

    from app import create_app
    app = create_app(data_dir=tmp, start_osc=False)

    from storage.json_store import JsonStore
    from api import devices as devices_mod
    from api import vents_control as vents_control_mod
    devices_mod.store = JsonStore(tmp, "devices", "dev")
    vents_control_mod.device_store = devices_mod.store

    dev = devices_mod.store.create({
        "name": "vents-1",
        "ip_address": "192.168.1.50",
        "osc_port": 9000,
        "type": "vents",
    })
    with app.test_client() as c:
        yield c, dev


def test_rejects_unknown_command(ctx):
    client, dev = ctx
    resp = client.post(
        f"/api/v1/vents-control/{dev['id']}/command",
        data=json.dumps({"command": "teleport", "value": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_rejects_non_vents_device(ctx):
    client, _ = ctx
    from api import devices as devices_mod
    tr = devices_mod.store.create({
        "name": "T",
        "ip_address": "192.168.1.70",
        "osc_port": 9000,
        "type": "trolley",
    })
    resp = client.post(
        f"/api/v1/vents-control/{tr['id']}/command",
        data=json.dumps({"command": "target", "value": 20}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_peltier_dispatches_indexed_address(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "peltier", "index": 2, "value": 1}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once_with("192.168.1.50", 9000, "/vents/peltier/2", 1)


def test_peltier_mask_packs_bits(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "peltier_mask", "value": 0b101}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/peltier"
        assert args[3] == 0b101


def test_fan_clamps_and_dispatches(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "fan", "index": 1, "value": 2.0}),  # out of range
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/fan/1"
        assert args[3] == pytest.approx(1.0)  # clamped


def test_mode_accepts_raw_auto(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        for m in ("raw", "auto"):
            client.post(
                f"/api/v1/vents-control/{dev['id']}/command",
                data=json.dumps({"command": "mode", "value": m}),
                content_type="application/json",
            )
        assert mock_osc.send.call_count == 2


def test_mode_rejects_bogus(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "mode", "value": "banana"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


def test_target_dispatches_float(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "target", "value": 18.5}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/target"
        assert args[3] == pytest.approx(18.5)


def test_status_reads_receiver(ctx):
    client, dev = ctx
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    r.vents_status["192.168.1.50"] = {
        "temp1_c": 22.1, "temp2_c": 18.3,
        "fan1": 0.5, "fan2": 0.8,
        "peltier_mask": 0b101, "peltier": [True, False, True],
        "rpm1A": 1200, "rpm1B": 1150, "rpm2A": 1400, "rpm2B": 1380,
        "target_c": 20.0, "mode": "auto", "state": "cooling",
        "timestamp": 1e12,
    }
    r.last_seen["192.168.1.50"] = 1e12
    with patch("api.vents_control._osc"):
        resp = client.get(f"/api/v1/vents-control/{dev['id']}/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["temp1_c"] == pytest.approx(22.1)
    assert body["mode"] == "auto"
    assert body["state"] == "cooling"
    assert body["online"] is True
