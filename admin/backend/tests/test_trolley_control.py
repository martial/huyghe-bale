"""Tests for the trolley-control blueprint — raw OSC commands + status readout."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """Build the app against a scratch data dir, using the blueprints' own stores
    to create fixtures so the module-level JsonStore bindings line up."""
    tmp = str(tmp_path)
    for sub in ("devices", "trolley_timelines"):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)

    from app import create_app
    app = create_app(data_dir=tmp, start_osc=False)

    # Re-point the module-level stores at the test dir (they were bound on
    # first import and don't follow config.DATA_DIR changes).
    from storage.json_store import JsonStore
    from api import devices as devices_mod
    from api import trolley_control as trolley_control_mod
    devices_mod.store = JsonStore(tmp, "devices", "dev")
    trolley_control_mod.device_store = devices_mod.store

    dev = devices_mod.store.create({
        "name": "Rail-1",
        "ip_address": "192.168.1.77",
        "osc_port": 9000,
        "type": "trolley",
    })
    with app.test_client() as c:
        yield c, dev


def test_rejects_unknown_command(ctx):
    client, dev = ctx
    resp = client.post(
        f"/api/v1/trolley-control/{dev['id']}/command",
        data=json.dumps({"command": "teleport", "value": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_rejects_non_trolley_device(ctx):
    client, _ = ctx
    from api import devices as devices_mod
    vents = devices_mod.store.create({
        "name": "V",
        "ip_address": "192.168.1.70",
        "osc_port": 9000,
        "type": "vents",
    })
    resp = client.post(
        f"/api/v1/trolley-control/{vents['id']}/command",
        data=json.dumps({"command": "enable", "value": 1}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_sends_osc_for_enable(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "enable", "value": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        mock_osc.send.assert_called_once_with("192.168.1.77", 9000, "/trolley/enable", 1)


def test_sends_osc_for_accel(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "accel", "value": 1.5}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/trolley/accel"
        assert args[3] == pytest.approx(1.5)


def test_sends_osc_for_decel(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "decel", "value": 0.8}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/trolley/decel"
        assert args[3] == pytest.approx(0.8)


def test_sends_osc_for_position(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "position", "value": 0.75}),
            content_type="application/json",
        )
        mock_osc.send.assert_called_once()
        args = mock_osc.send.call_args[0]
        assert args[2] == "/trolley/position"
        assert args[3] == pytest.approx(0.75)


def test_status_reads_receiver(ctx):
    client, dev = ctx
    # Seed the receiver's trolley_status as if a Pi had pushed a frame.
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    r.trolley_status["192.168.1.77"] = {
        "position": 0.42, "limit": 0, "homed": 1,
        "state": "idle", "calibrated": 1, "enabled": 1, "timestamp": 123.0,
    }
    r.last_seen["192.168.1.77"] = 1e12  # pretend "just now"

    resp = client.get(f"/api/v1/trolley-control/{dev['id']}/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["position"] == pytest.approx(0.42)
    assert body["homed"] == 1
    assert body["calibrated"] == 1
    assert body["state"] == "idle"
    assert body["enabled"] == 1
    assert body["online"] is True


def test_home_with_direction_sends_string(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "home", "value": "forward"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        mock_osc.send.assert_called_once_with(
            "192.168.1.77", 9000, "/trolley/home", "forward",
        )


def test_calibrate_commands_no_longer_recognised(ctx):
    client, dev = ctx
    for cmd in ("calibrate_start", "calibrate_stop", "calibrate_save", "calibrate_cancel"):
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": cmd}),
            content_type="application/json",
        )
        assert resp.status_code == 400, cmd


def test_config_set_sends_key_value_pair(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({
                "command": "config_set",
                "key": "soft_limit_pct", "value": 0.95,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        mock_osc.send.assert_called_once_with(
            "192.168.1.77", 9000, "/trolley/config/set",
            ["soft_limit_pct", 0.95],
        )


def test_config_set_rejects_missing_key(ctx):
    client, dev = ctx
    resp = client.post(
        f"/api/v1/trolley-control/{dev['id']}/command",
        data=json.dumps({"command": "config_set", "value": 1.0}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_speed_command_clamps_to_safety_cap(ctx):
    client, dev = ctx
    from api.trolley_control import MAX_SPEED_PCT
    with patch("api.trolley_control._osc") as mock_osc:
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "speed", "value": 1.0}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        args = mock_osc.send.call_args[0]
        assert args[2] == "/trolley/speed"
        assert args[3] == pytest.approx(MAX_SPEED_PCT)


def test_speed_command_passes_below_cap(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "speed", "value": 0.2}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[3] == pytest.approx(0.2)


def test_alarm_reset_sends_osc(ctx):
    client, dev = ctx
    with patch("api.trolley_control._osc") as mock_osc:
        resp = client.post(
            f"/api/v1/trolley-control/{dev['id']}/command",
            data=json.dumps({"command": "alarm_reset"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        args = mock_osc.send.call_args[0]
        assert args[2] == "/trolley/alarm/reset"
