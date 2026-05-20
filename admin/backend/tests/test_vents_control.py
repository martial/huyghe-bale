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


def test_target_hot_dispatches_to_hot_address(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "target_hot", "value": 22.0}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/target/hot"
        assert args[3] == pytest.approx(22.0)


def test_target_cold_dispatches_to_cold_address(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "target_cold", "value": 18.0}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/target/cold"
        assert args[3] == pytest.approx(18.0)


def test_target_active_dispatches_to_active_address(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        for v in ("hot", "cold"):
            client.post(
                f"/api/v1/vents-control/{dev['id']}/command",
                data=json.dumps({"command": "target_active", "value": v}),
                content_type="application/json",
            )
        assert mock_osc.send.call_count == 2
        for call_args, expected in zip(mock_osc.send.call_args_list, ("hot", "cold")):
            args = call_args[0]
            assert args[2] == "/vents/target/active"
            assert args[3] == expected


def test_target_active_rejects_garbage(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "target_active", "value": "lukewarm"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


_VALID_ID = "28-aaaaaaaaaaaa"


def test_probe_assign_hot_dispatches_rom_id(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "probe_assign_hot", "value": _VALID_ID}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/probe/assign_hot"
        assert args[3] == _VALID_ID


def test_probe_assign_cold_dispatches_rom_id(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "probe_assign_cold", "value": "28-bbbbbbbbbbbb"}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/probe/assign_cold"
        assert args[3] == "28-bbbbbbbbbbbb"


def test_probe_assign_rejects_invalid_rom_id(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "probe_assign_hot", "value": "not-a-rom"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


def test_probe_assign_rejects_wrong_family_prefix(ctx):
    # DS18B20 family is 28-; a 10- (DS18S20) prefix must be rejected.
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "probe_assign_hot", "value": "10-aaaaaaaaaaaa"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


def test_probe_clear_accepts_hot_cold_both(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        for v in ("hot", "cold", "both"):
            resp = client.post(
                f"/api/v1/vents-control/{dev['id']}/command",
                data=json.dumps({"command": "probe_clear", "value": v}),
                content_type="application/json",
            )
            assert resp.status_code == 200
        # Three OSC sends, each to /vents/probe/clear with the value
        assert mock_osc.send.call_count == 3
        for call_args, expected in zip(mock_osc.send.call_args_list, ("hot", "cold", "both")):
            args = call_args[0]
            assert args[2] == "/vents/probe/clear"
            assert args[3] == expected


def test_probe_clear_rejects_garbage(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "probe_clear", "value": "all"}),
            content_type="application/json",
        )
    assert resp.status_code == 400


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
    with patch("api.vents_control._osc"), \
         patch("api.vents_control._fetch_snapshot", return_value=None):
        resp = client.get(f"/api/v1/vents-control/{dev['id']}/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["temp1_c"] == pytest.approx(22.1)
    assert body["mode"] == "auto"
    assert body["state"] == "cooling"
    assert body["online"] is True


def test_status_merges_snapshot_probe_fields(ctx):
    """When the Pi's HTTP snapshot returns probes[] + dual-setpoint fields,
    /status merges them on top of the OSC snapshot — this is how the admin
    learns about the discovered ROM ids and per-probe live temps."""
    client, dev = ctx
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    r.vents_status["192.168.1.50"] = {
        "temp1_c": 22.1, "temp2_c": 18.3,
        "fan1": 0.0, "fan2": 0.0,
        "peltier_mask": 0, "peltier": [False, False, False],
        "rpm1A": 0, "rpm1B": 0, "rpm2A": 0, "rpm2B": 0,
        "target_c": 22.0, "mode": "auto", "state": "probe_unassigned",
        "timestamp": 1e12,
    }
    r.last_seen["192.168.1.50"] = 1e12
    snapshot = {
        "ok": True,
        "probes": [
            {"id": "28-aaaaaaaaaaaa", "temp_c": 22.1},
            {"id": "28-bbbbbbbbbbbb", "temp_c": 18.3},
        ],
        "probe_hot_id": None,
        "probe_cold_id": None,
        "temp_hot_c": None,
        "temp_cold_c": None,
        "hot_target_c": 22.0,
        "cold_target_c": 18.0,
        "active_target": "cold",
    }
    with patch("api.vents_control._osc"), \
         patch("api.vents_control._fetch_snapshot", return_value=snapshot):
        resp = client.get(f"/api/v1/vents-control/{dev['id']}/status")
    body = resp.get_json()
    assert body["state"] == "probe_unassigned"
    assert body["hot_target_c"] == 22.0
    assert body["cold_target_c"] == 18.0
    assert body["active_target"] == "cold"
    assert body["probe_hot_id"] is None
    assert len(body["probes"]) == 2
    assert body["probes"][0]["id"] == "28-aaaaaaaaaaaa"


def test_unique_peltier_on_dispatches_int_1(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "unique_peltier", "value": True}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/unique_peltier"
        assert args[3] == 1


def test_unique_peltier_off_dispatches_int_0(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "unique_peltier", "value": False}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/unique_peltier"
        assert args[3] == 0


def test_peltier_rest_s_dispatches_seconds(ctx):
    client, dev = ctx
    with patch("api.vents_control._osc") as mock_osc:
        client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "peltier_rest_s", "value": 300}),
            content_type="application/json",
        )
        args = mock_osc.send.call_args[0]
        assert args[2] == "/vents/peltier_rest_s"
        assert args[3] == 300


@pytest.mark.parametrize("value", [-1, 3601, 999999])
def test_peltier_rest_s_rejects_out_of_range(ctx, value):
    client, dev = ctx
    with patch("api.vents_control._osc"):
        resp = client.post(
            f"/api/v1/vents-control/{dev['id']}/command",
            data=json.dumps({"command": "peltier_rest_s", "value": value}),
            content_type="application/json",
        )
    assert resp.status_code == 400


def test_status_merges_unique_peltier_snapshot_fields(ctx):
    """When the Pi's HTTP snapshot carries the unique-peltier fields, they
    flow through to /status — including the per-cell rest_remaining array
    which the OSC broadcast does not carry."""
    client, dev = ctx
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    r.vents_status["192.168.1.50"] = {
        "temp1_c": 22.1, "temp2_c": 18.3,
        "fan1": 0.0, "fan2": 0.0,
        "peltier_mask": 1, "peltier": [True, False, False],
        "rpm1A": 0, "rpm1B": 0, "rpm2A": 0, "rpm2B": 0,
        "target_c": 22.0, "mode": "auto", "state": "heating",
        "timestamp": 1e12,
    }
    r.last_seen["192.168.1.50"] = 1e12
    snapshot = {
        "ok": True,
        "unique_peltier": 1,
        "peltier_rest_s": 600,
        "active_peltier_index": 0,
        "peltier_rest_remaining": [0.0, 540.0, 540.0],
    }
    with patch("api.vents_control._osc"), \
         patch("api.vents_control._fetch_snapshot", return_value=snapshot):
        resp = client.get(f"/api/v1/vents-control/{dev['id']}/status")
    body = resp.get_json()
    assert body["unique_peltier"] == 1
    assert body["peltier_rest_s"] == 600
    assert body["active_peltier_index"] == 0
    assert body["peltier_rest_remaining"] == [0.0, 540.0, 540.0]


def test_status_skips_snapshot_fetch_when_offline(ctx):
    """If the device is offline (no OSC pong within timeout) we skip the
    HTTP call — there's no Pi to talk to and connect-timeout would slow
    every poll."""
    client, dev = ctx
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    # OscReceiver is a singleton — clear any leftover last_seen from sibling
    # tests so this device reads as offline.
    r.last_seen.pop("192.168.1.50", None)
    with patch("api.vents_control._osc"), \
         patch("api.vents_control._fetch_snapshot") as mock_fetch:
        client.get(f"/api/v1/vents-control/{dev['id']}/status")
    mock_fetch.assert_not_called()
