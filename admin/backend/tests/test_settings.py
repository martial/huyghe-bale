"""Tests for /api/v1/settings — defaults, validation, and per-device push."""

import json
import os

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    tmp = str(tmp_path)
    os.makedirs(os.path.join(tmp, "devices"), exist_ok=True)

    from app import create_app

    app = create_app(data_dir=tmp, start_osc=False)

    from storage.json_store import JsonStore
    from api import devices as devices_mod
    from api import settings as settings_mod

    # Repoint the settings module's store at the same tmp dir the app uses.
    devices_mod.store = JsonStore(tmp, "devices", "dev")
    settings_mod.SETTINGS_FILE = os.path.join(tmp, "settings.json")
    settings_mod.device_store = devices_mod.store

    devices_mod.store.create(
        {"name": "v1", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"}
    )
    devices_mod.store.create(
        {"name": "v2", "ip_address": "10.0.0.2", "osc_port": 9000, "type": "vents"}
    )
    devices_mod.store.create(
        {"name": "t1", "ip_address": "10.0.0.3", "osc_port": 9000, "type": "trolley"}
    )

    with app.test_client() as c:
        yield c, settings_mod, devices_mod


def test_get_settings_returns_new_defaults(client):
    c, _, _ = client
    r = c.get("/api/v1/settings")
    body = r.get_json()
    assert body["vents_min_fan_pct"] == 20.0
    assert body["vents_min_rpm_alarm"] == 500
    assert body["vents_over_temp_fan_pct"] == 100.0


def test_put_min_fan_pct_pushes_to_vents_devices_only(monkeypatch, client):
    c, settings_mod, _ = client
    pushed = []

    def fake_urlopen(req, timeout=None):
        pushed.append({
            "url": req.full_url,
            "body": json.loads(req.data.decode("utf-8")),
        })
        class _R:
            def read(self): return b"{}"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _R()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    r = c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_min_fan_pct": 30}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["vents_min_fan_pct"] == 30.0

    # 2 vents devices, 0 trolley
    assert len(pushed) == 2
    assert all("10.0.0.1" in p["url"] or "10.0.0.2" in p["url"] for p in pushed)
    assert all(p["body"] == {"command": "min_fan_pct", "value": 30.0} for p in pushed)


def test_put_over_temp_fan_pct_pushes_correct_command(monkeypatch, client):
    c, _, _ = client
    pushed = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: pushed.append(json.loads(req.data.decode("utf-8"))) or _MockResp(),
    )

    r = c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_over_temp_fan_pct": 75}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert all(p == {"command": "over_temp_fan_pct", "value": 75.0} for p in pushed)


def test_put_max_fan_pct_pushes_to_vents_devices_only(monkeypatch, client):
    c, _, _ = client
    pushed = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: pushed.append({
            "url": req.full_url,
            "body": json.loads(req.data.decode("utf-8")),
        }) or _MockResp(),
    )

    r = c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_max_fan_pct": 60}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["vents_max_fan_pct"] == 60.0

    # Two vents devices, no trolleys → exactly two pushes.
    assert len(pushed) == 2
    assert all(p["body"] == {"command": "max_fan_pct", "value": 60.0} for p in pushed)


def test_legacy_output_cap_is_filtered_from_response(client):
    """Legacy persisted output_cap values must not appear in GET — the field
    moved to the Pi as vents_max_fan_pct."""
    c, settings_mod, _ = client
    # Write a settings file that simulates an upgrade from the old schema.
    with open(settings_mod.SETTINGS_FILE, "w") as f:
        json.dump({"osc_frequency": 30, "output_cap": 70}, f)
    r = c.get("/api/v1/settings")
    body = r.get_json()
    assert "output_cap" not in body
    assert body["vents_max_fan_pct"] == 100.0  # default kicks in


def test_put_min_rpm_alarm_does_not_push_to_devices(monkeypatch, client):
    c, _, _ = client
    pushed = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: pushed.append(req) or _MockResp(),
    )

    r = c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_min_rpm_alarm": 800}),
        content_type="application/json",
    )
    assert r.status_code == 200
    # Admin-side only — never POST to a Pi.
    assert pushed == []


def test_put_min_rpm_alarm_propagates_to_receiver(monkeypatch, client):
    c, _, _ = client
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _MockResp()
    )

    from engine.osc_receiver import OscReceiver
    OscReceiver().set_min_rpm_alarm(0)  # baseline
    c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_min_rpm_alarm": 650}),
        content_type="application/json",
    )
    assert OscReceiver().min_rpm_alarm == 650


def test_put_rejects_out_of_range_values(client):
    c, _, _ = client
    cases = [
        ({"vents_min_fan_pct": 150}, "vents_min_fan_pct"),
        ({"vents_min_fan_pct": -1}, "vents_min_fan_pct"),
        ({"vents_min_rpm_alarm": -10}, "vents_min_rpm_alarm"),
        ({"vents_min_rpm_alarm": 99999}, "vents_min_rpm_alarm"),
        ({"vents_over_temp_fan_pct": 200}, "vents_over_temp_fan_pct"),
    ]
    for body, key in cases:
        r = c.put(
            "/api/v1/settings",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert r.status_code == 400, f"expected 400 for {body}"
        assert key in r.get_json()["error"]


def test_put_unchanged_value_does_not_push(monkeypatch, client):
    c, _, _ = client
    pushed = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: pushed.append(req) or _MockResp(),
    )

    # Set once
    c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_min_fan_pct": 25}),
        content_type="application/json",
    )
    assert len(pushed) == 2  # 2 vents devices on first PUT
    pushed.clear()

    # Same value again — must not re-push
    c.put(
        "/api/v1/settings",
        data=json.dumps({"vents_min_fan_pct": 25}),
        content_type="application/json",
    )
    assert pushed == []


class _MockResp:
    def read(self): return b"{}"
    def __enter__(self): return self
    def __exit__(self, *a): return False
