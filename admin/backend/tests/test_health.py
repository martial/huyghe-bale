"""Shape-test for /api/v1/health — the endpoint the launcher's error
dialog depends on and the frontend HealthBanner polls."""

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    # start_osc=False keeps the real UDP server out of unit tests.
    import os
    os.makedirs(os.path.join(str(tmp_path), "devices"), exist_ok=True)
    app = create_app(data_dir=str(tmp_path), start_osc=False)
    app.testing = True

    # Rebind the module-level device store onto this tmp dir. Same trick
    # as test_vents_control.py — necessary because health.py reads from
    # `api.devices.store` directly (a singleton that defaults to the
    # production DATA_DIR), so without this each test would see whatever
    # devices a sibling test wrote to its own tmp_path.
    from storage.json_store import JsonStore
    from api import devices as devices_mod
    from api import health as health_mod
    devices_mod.store = JsonStore(str(tmp_path), "devices", "dev")
    # health imported `from api.devices import store as device_store` so it
    # holds its own local reference — rebind that too.
    health_mod.device_store = devices_mod.store

    with app.test_client() as c:
        yield c


def test_health_payload_shape(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()

    # Every subsystem is reported, even when disabled.
    assert "osc_receiver" in body
    assert "bridge" in body
    assert "playback" in body
    assert "ok" in body
    assert "log_path" in body

    assert "running" in body["osc_receiver"]
    assert "port" in body["osc_receiver"]
    assert "error" in body["osc_receiver"]

    assert "running" in body["bridge"]
    assert "error" in body["bridge"]

    assert "thread_alive" in body["playback"]
    assert "last_error" in body["playback"]


def test_health_ok_true_when_no_errors(client):
    resp = client.get("/api/v1/health")
    body = resp.get_json()
    # Receiver didn't start (start_osc=False), but no error was recorded
    # either. Bridge is idle. Playback hasn't run. ok should be True.
    assert body["osc_receiver"]["error"] is None
    assert body["bridge"]["error"] is None
    assert body["playback"]["last_error"] is None
    assert body["ok"] is True


def test_health_includes_vents_aggregates(client):
    resp = client.get("/api/v1/health")
    body = resp.get_json()
    # Both vents aggregates are always present (possibly empty arrays) so
    # the frontend's banner code can render unconditionally.
    assert "vents_over_temp" in body
    assert "vents_probe_unassigned" in body
    assert isinstance(body["vents_over_temp"], list)
    assert isinstance(body["vents_probe_unassigned"], list)


def test_health_surfaces_probe_unassigned_devices(client):
    """A vents device whose state is `probe_unassigned` lands in the
    aggregate so the SystemWarnings banner can prompt the operator to
    run the touch-test."""
    from api import devices as devices_mod
    from engine.osc_receiver import OscReceiver

    dev = devices_mod.store.create({
        "name": "vents-probe-test",
        "ip_address": "10.99.0.1",
        "osc_port": 9000,
        "type": "vents",
    })
    receiver = OscReceiver(port=9001)
    receiver.vents_status["10.99.0.1"] = {
        "state": "probe_unassigned",
        "probe_hot_id": None,
        "probe_cold_id": None,
        "probes": [
            {"id": "28-aaaaaaaaaaaa", "temp_c": 22.5},
            {"id": "28-bbbbbbbbbbbb", "temp_c": 18.0},
        ],
        "timestamp": 1e12,
    }
    try:
        body = client.get("/api/v1/health").get_json()
        items = body["vents_probe_unassigned"]
        match = next((i for i in items if i["device_id"] == dev["id"]), None)
        assert match is not None
        assert match["probe_hot_id"] is None
        assert set(match["discovered"]) == {"28-aaaaaaaaaaaa", "28-bbbbbbbbbbbb"}
    finally:
        receiver.vents_status.pop("10.99.0.1", None)


def test_health_over_temp_includes_dual_fields(client):
    from api import devices as devices_mod
    from engine.osc_receiver import OscReceiver

    dev = devices_mod.store.create({
        "name": "vents-overtemp-test",
        "ip_address": "10.99.0.2",
        "osc_port": 9000,
        "type": "vents",
    })
    receiver = OscReceiver(port=9001)
    receiver.vents_status["10.99.0.2"] = {
        "state": "over_temp",
        "temp1_c": 95.0, "temp2_c": 25.0,
        "target_c": 25.0, "max_temp_c": 80.0,
        "temp_hot_c": 95.0, "temp_cold_c": 25.0,
        "hot_target_c": 25.0, "cold_target_c": 18.0,
        "timestamp": 1e12,
    }
    try:
        body = client.get("/api/v1/health").get_json()
        match = next((i for i in body["vents_over_temp"] if i["device_id"] == dev["id"]), None)
        assert match is not None
        assert match["temp_hot_c"] == 95.0
        assert match["temp_cold_c"] == 25.0
        assert match["hot_target_c"] == 25.0
        assert match["cold_target_c"] == 18.0
    finally:
        receiver.vents_status.pop("10.99.0.2", None)
