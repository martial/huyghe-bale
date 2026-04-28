"""POST /api/v1/playback/start refuses trolley timelines whose target
trolleys haven't been calibrated. Without this guard the firmware would
silently no-op /trolley/position and the show would visibly stall."""

import json
import os
import time

import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    for sub in ("devices", "trolley_timelines"):
        os.makedirs(os.path.join(str(tmp_path), sub), exist_ok=True)

    from app import create_app
    app = create_app(data_dir=str(tmp_path), start_osc=False)

    from storage.json_store import JsonStore
    from api import devices as devices_api
    from api import playback as playback_api
    fresh_devices = JsonStore(str(tmp_path), "devices", "dev")
    monkeypatch.setattr(devices_api, "store", fresh_devices)
    monkeypatch.setattr(playback_api, "device_store", fresh_devices)
    monkeypatch.setattr(playback_api, "trolley_timeline_store",
                        JsonStore(str(tmp_path), "trolley_timelines", "trtl"))

    trolley_dev = fresh_devices.create({
        "name": "T1", "ip_address": "10.0.0.50",
        "osc_port": 9000, "type": "trolley",
    })

    # Seed a minimal trolley timeline.
    tl_store = JsonStore(str(tmp_path), "trolley_timelines", "trtl")
    timeline = tl_store.create({
        "name": "rail",
        "duration": 5.0,
        "events": [{"id": "e1", "time": 0, "command": "position", "value": 0.5}],
    })

    # The OscReceiver is a long-lived singleton; clear just the IP we care about
    # rather than recreating the singleton, which would orphan module-level
    # references like api.trolley_control._receiver.
    from engine.osc_receiver import OscReceiver
    receiver = OscReceiver(port=9001)
    receiver.trolley_status.pop("10.0.0.50", None)

    return {
        "client": app.test_client(),
        "device": trolley_dev,
        "timeline": timeline,
    }


def _start(ctx, **overrides):
    body = {
        "type": "trolley-timeline",
        "id": ctx["timeline"]["id"],
        "device_ids": [ctx["device"]["id"]],
    }
    body.update(overrides)
    return ctx["client"].post(
        "/api/v1/playback/start", json=body,
    )


def test_refuses_uncalibrated_trolley(ctx):
    # No /trolley/status ever received → calibrated defaults to absent.
    resp = _start(ctx)
    assert resp.status_code == 400
    body = resp.get_json()
    assert "uncalibrated_devices" in body
    assert body["uncalibrated_devices"][0]["ip"] == "10.0.0.50"


def test_allows_calibrated_trolley(ctx):
    from engine.osc_receiver import OscReceiver
    r = OscReceiver(port=9001)
    r.trolley_status["10.0.0.50"] = {
        "position": 0.0, "limit": 0, "homed": 1,
        "state": "idle", "calibrated": 1, "timestamp": time.time(),
    }
    resp = _start(ctx)
    assert resp.status_code == 200, resp.get_json()
    # Tear down the playback thread so the fixture cleanup is fast.
    ctx["client"].post("/api/v1/playback/stop")
