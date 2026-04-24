"""Exhaustive OSC-wire matrix — one named test per admin UI trigger.

Each test replaces every OSC-sender attachment point with a
`RecordingSender` that logs every `send` call, drives the trigger
(HTTP route or engine method), then asserts the recorded
`(ip, port, address, value)` tuples exactly match the expected wire
shape.

These tests prove *intent* — i.e. the right address + arg leaves the
backend. Actual delivery to hardware is covered by the sibling
`OSC_RUNBOOK.md`, which a human walks through with real Pis connected.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app import create_app


class RecordingSender:
    """Drop-in for OscSender that captures every call as a tuple."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, int, str, Any]] = []

    # --- `OscSender.send(ip, port, address, value)` ---
    def send(self, ip: str, port: int, address: str, value: Any) -> None:
        self.sends.append((ip, port, address, value))

    # --- `OscSender.send_values(ip, port, address, values=None)` ---
    def send_values(self, ip: str, port: int, address: str, values=None) -> None:
        if not values:
            self.sends.append((ip, port, address, None))
        elif len(values) == 1:
            self.sends.append((ip, port, address, values[0]))
        else:
            self.sends.append((ip, port, address, list(values)))

    # --- `OscSender.send_zero(ip, port)` — matches the real implementation ---
    def send_zero(self, ip: str, port: int) -> None:
        self.sends.append((ip, port, "/vents/fan/1", 0.0))
        self.sends.append((ip, port, "/vents/fan/2", 0.0))
        self.sends.append((ip, port, "/vents/peltier", 0))


# --- fixtures -----------------------------------------------------------


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """Build an app, seed two devices (vents + trolley), install the
    recording sender across every OSC attachment point.

    Each api module creates its `store = JsonStore(DATA_DIR, …)` at
    first import, then caches. Running under the full suite means the
    module's store was captured with an earlier test's tmp_path and
    won't see this test's device records unless we re-point it.
    """
    app = create_app(start_osc=False, data_dir=str(tmp_path))
    client = app.test_client()

    import os
    from storage.json_store import JsonStore
    from api import (
        devices as devices_api,
        timelines as timelines_api,
        trolley_timelines as trolley_timelines_api,
        orchestrations as orch_api,
        playback as playback_api,
    )

    # Rebind each cached store onto this test's tmp_path so seeded
    # devices are discoverable.
    for mod, entity, prefix in (
        (devices_api, "devices", "dev"),
        (timelines_api, "timelines", "tl"),
        (trolley_timelines_api, "trolley_timelines", "trtl"),
        (orch_api, "orchestrations", "orch"),
    ):
        fresh = JsonStore(str(tmp_path), entity, prefix)
        monkeypatch.setattr(mod, "store", fresh, raising=False)

    # playback_api has four stores; rebind each.
    monkeypatch.setattr(playback_api, "timeline_store",
                        JsonStore(str(tmp_path), "timelines", "tl"))
    monkeypatch.setattr(playback_api, "device_store",
                        JsonStore(str(tmp_path), "devices", "dev"))
    monkeypatch.setattr(playback_api, "orchestration_store",
                        JsonStore(str(tmp_path), "orchestrations", "orch"))
    monkeypatch.setattr(playback_api, "trolley_timeline_store",
                        JsonStore(str(tmp_path), "trolley_timelines", "trtl"))

    # vents_control, trolley_control, health, settings each keep their
    # own `device_store` alias captured via `from api.devices import
    # store as device_store` — rebind those too. protocol_test reads
    # devices via the module-level `devices_api.store` (already rebound
    # above), so it picks up the rebind automatically.
    from api import vents_control, trolley_control, health as health_api, settings as settings_api
    for mod in (vents_control, trolley_control, health_api, settings_api):
        monkeypatch.setattr(mod, "device_store", devices_api.store, raising=False)

    # Ensure the subdirs exist for this test.
    for sub in ("devices", "timelines", "trolley_timelines", "orchestrations"):
        os.makedirs(os.path.join(str(tmp_path), sub), exist_ok=True)

    sender = RecordingSender()

    # Module-level _osc / osc refs that emit OSC to the Pi.
    from api import vents_control, trolley_control, protocol_test
    monkeypatch.setattr(vents_control, "_osc", sender)
    monkeypatch.setattr(trolley_control, "_osc", sender)
    monkeypatch.setattr(protocol_test, "_osc", sender)
    monkeypatch.setattr(devices_api, "osc", sender)

    # Playback engine's own sender.
    monkeypatch.setattr(playback_api._engine, "osc", sender)

    # Bridge sender (bridge may or may not exist depending on settings).
    from api import bridge as bridge_api
    if bridge_api._bridge is not None:
        monkeypatch.setattr(bridge_api._bridge, "_osc", sender)

    # Seed two devices so every surface has a target.
    vents = devices_api.store.create({
        "name": "vents-1", "ip_address": "10.0.0.1",
        "osc_port": 9000, "type": "vents",
    })
    trolley = devices_api.store.create({
        "name": "trolley-1", "ip_address": "10.0.0.2",
        "osc_port": 9000, "type": "trolley",
    })

    return {
        "client": client,
        "sender": sender,
        "vents_id": vents["id"],
        "trolley_id": trolley["id"],
        "engine": playback_api._engine,
    }


def _only_command_sends(sends, ip=None):
    """Drop any /sys/ping preambles (status handler fires one) so the
    assertion focuses on the command under test."""
    out = [s for s in sends if s[2] != "/sys/ping"]
    return [s for s in out if ip is None or s[0] == ip]


# --- Vents test panel (V1..V12) -----------------------------------------


def _vents_cmd(ctx, body):
    return ctx["client"].post(
        f"/api/v1/vents-control/{ctx['vents_id']}/command", json=body,
    )


class TestVentsPanel:
    def test_V1_mode_raw(self, ctx):
        r = _vents_cmd(ctx, {"command": "mode", "value": "raw"})
        assert r.status_code == 200
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/mode", "raw")]

    def test_V2_mode_auto(self, ctx):
        _vents_cmd(ctx, {"command": "mode", "value": "auto"})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/mode", "auto")]

    def test_V3_target(self, ctx):
        _vents_cmd(ctx, {"command": "target", "value": 22.5})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.1", 9000, "/vents/target")
        assert math.isclose(val, 22.5)
        assert isinstance(val, float)

    def test_V4_peltier_1_on(self, ctx):
        _vents_cmd(ctx, {"command": "peltier", "index": 1, "value": 1})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier/1", 1)]

    def test_V5_peltier_1_off(self, ctx):
        _vents_cmd(ctx, {"command": "peltier", "index": 1, "value": 0})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier/1", 0)]

    def test_V6_peltier_2_on(self, ctx):
        _vents_cmd(ctx, {"command": "peltier", "index": 2, "value": 1})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier/2", 1)]

    def test_V7_peltier_3_on(self, ctx):
        _vents_cmd(ctx, {"command": "peltier", "index": 3, "value": 1})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier/3", 1)]

    def test_V8_peltier_mask_clear(self, ctx):
        _vents_cmd(ctx, {"command": "peltier_mask", "value": 0})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier", 0)]

    def test_V9_peltier_mask_all(self, ctx):
        _vents_cmd(ctx, {"command": "peltier_mask", "value": 7})
        assert ctx["sender"].sends == [("10.0.0.1", 9000, "/vents/peltier", 7)]

    def test_V10_fan_1_half(self, ctx):
        _vents_cmd(ctx, {"command": "fan", "index": 1, "value": 0.5})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.1", 9000, "/vents/fan/1")
        assert math.isclose(val, 0.5)
        assert isinstance(val, float)

    def test_V11_fan_2_high(self, ctx):
        _vents_cmd(ctx, {"command": "fan", "index": 2, "value": 0.8})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.1", 9000, "/vents/fan/2")
        assert math.isclose(val, 0.8)

    def test_V12_max_temp(self, ctx):
        _vents_cmd(ctx, {"command": "max_temp", "value": 80})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.1", 9000, "/vents/max_temp")
        assert math.isclose(val, 80.0)
        assert isinstance(val, float)

    def test_fan_value_out_of_range_is_clamped(self, ctx):
        """Sanity — the route clamps to [0,1] so a careless UI can't
        drive a Pi beyond the safe PWM duty range."""
        _vents_cmd(ctx, {"command": "fan", "index": 1, "value": 1.5})
        assert ctx["sender"].sends[-1][3] == 1.0
        _vents_cmd(ctx, {"command": "fan", "index": 1, "value": -0.3})
        assert ctx["sender"].sends[-1][3] == 0.0

    def test_peltier_mask_extra_bits_stripped(self, ctx):
        _vents_cmd(ctx, {"command": "peltier_mask", "value": 0xFF})
        assert ctx["sender"].sends[-1][3] == 0b111

    def test_unknown_vents_command_rejected(self, ctx):
        r = _vents_cmd(ctx, {"command": "boom"})
        assert r.status_code == 400
        assert ctx["sender"].sends == []

    def test_vents_command_on_trolley_rejected(self, ctx):
        r = ctx["client"].post(
            f"/api/v1/vents-control/{ctx['trolley_id']}/command",
            json={"command": "mode", "value": "raw"},
        )
        assert r.status_code == 400
        assert ctx["sender"].sends == []


# --- Trolley test panel (T1..T9) ---------------------------------------


def _trolley_cmd(ctx, body):
    return ctx["client"].post(
        f"/api/v1/trolley-control/{ctx['trolley_id']}/command", json=body,
    )


class TestTrolleyPanel:
    def test_T1_enable_on(self, ctx):
        _trolley_cmd(ctx, {"command": "enable", "value": 1})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/enable", 1)]

    def test_T2_enable_off(self, ctx):
        _trolley_cmd(ctx, {"command": "enable", "value": 0})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/enable", 0)]

    def test_T3_dir_forward(self, ctx):
        _trolley_cmd(ctx, {"command": "dir", "value": 1})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/dir", 1)]

    def test_T4_dir_reverse(self, ctx):
        _trolley_cmd(ctx, {"command": "dir", "value": 0})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/dir", 0)]

    def test_T5_speed_half(self, ctx):
        _trolley_cmd(ctx, {"command": "speed", "value": 0.5})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.2", 9000, "/trolley/speed")
        assert math.isclose(val, 0.5)
        assert isinstance(val, float)

    def test_T6_step_1000(self, ctx):
        _trolley_cmd(ctx, {"command": "step", "value": 1000})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/step", 1000)]

    def test_T7_stop(self, ctx):
        _trolley_cmd(ctx, {"command": "stop"})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/stop", 0)]

    def test_T8_home(self, ctx):
        _trolley_cmd(ctx, {"command": "home"})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/home", 0)]

    def test_T9_position_quarter(self, ctx):
        _trolley_cmd(ctx, {"command": "position", "value": 0.25})
        ip, port, addr, val = ctx["sender"].sends[-1]
        assert (ip, port, addr) == ("10.0.0.2", 9000, "/trolley/position")
        assert math.isclose(val, 0.25)
        assert isinstance(val, float)

    def test_trolley_command_on_vents_rejected(self, ctx):
        r = ctx["client"].post(
            f"/api/v1/trolley-control/{ctx['vents_id']}/command",
            json={"command": "enable", "value": 1},
        )
        assert r.status_code == 400
        assert ctx["sender"].sends == []


# --- Vents timeline playback (VP1..VP4) -------------------------------


class TestVentsTimelinePlayback:
    def _timeline(self, a_val=0.4, b_val=0.7, duration=10.0):
        return {
            "id": "tl_x",
            "name": "unit",
            "duration": duration,
            "lanes": {
                "a": {"points": [{"time": 0, "value": a_val,
                                  "curve_type": "linear",
                                  "bezier_handles": None}]},
                "b": {"points": [{"time": 0, "value": b_val,
                                  "curve_type": "linear",
                                  "bezier_handles": None}]},
            },
        }

    def test_VP1_tick_sends_fan1_and_fan2(self, ctx):
        engine = ctx["engine"]
        engine.output_cap = 100
        engine._devices = [{"id": ctx["vents_id"], "ip_address": "10.0.0.1",
                            "osc_port": 9000, "type": "vents"}]
        engine._evaluate_and_send(self._timeline(0.4, 0.7), 0.0)
        assert ctx["sender"].sends == [
            ("10.0.0.1", 9000, "/vents/fan/1", pytest.approx(0.4)),
            ("10.0.0.1", 9000, "/vents/fan/2", pytest.approx(0.7)),
        ]

    def test_VP2_tick_respects_output_cap(self, ctx):
        engine = ctx["engine"]
        engine.output_cap = 50
        engine._devices = [{"id": ctx["vents_id"], "ip_address": "10.0.0.1",
                            "osc_port": 9000, "type": "vents"}]
        engine._evaluate_and_send(self._timeline(0.4, 0.7), 0.0)
        assert ctx["sender"].sends == [
            ("10.0.0.1", 9000, "/vents/fan/1", pytest.approx(0.2)),
            ("10.0.0.1", 9000, "/vents/fan/2", pytest.approx(0.35)),
        ]

    def test_VP3_fans_to_every_device(self, ctx):
        engine = ctx["engine"]
        engine.output_cap = 100
        engine._devices = [
            {"id": "a", "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"},
            {"id": "b", "ip_address": "10.0.0.10", "osc_port": 9000, "type": "vents"},
        ]
        engine._evaluate_and_send(self._timeline(0.4, 0.7), 0.0)
        addrs = [(ip, addr) for ip, _, addr, _ in ctx["sender"].sends]
        assert addrs == [
            ("10.0.0.1", "/vents/fan/1"), ("10.0.0.1", "/vents/fan/2"),
            ("10.0.0.10", "/vents/fan/1"), ("10.0.0.10", "/vents/fan/2"),
        ]

    def test_VP4_stop_zeroes_each_vents_device(self, ctx):
        """`engine.stop()` calls send_zero per device + /trolley/stop per trolley."""
        engine = ctx["engine"]
        engine._playback_type = "timeline"
        engine.playing = True
        engine._devices = [{"id": ctx["vents_id"], "ip_address": "10.0.0.1",
                            "osc_port": 9000, "type": "vents"}]
        engine.stop()
        assert ctx["sender"].sends == [
            ("10.0.0.1", 9000, "/vents/fan/1", 0.0),
            ("10.0.0.1", 9000, "/vents/fan/2", 0.0),
            ("10.0.0.1", 9000, "/vents/peltier", 0),
        ]


# --- Trolley timeline playback (TP1..TP9) -----------------------------


class TestTrolleyTimelinePlayback:
    def _setup_engine(self, ctx):
        engine = ctx["engine"]
        engine._devices = [{"id": ctx["trolley_id"], "ip_address": "10.0.0.2",
                            "osc_port": 9000, "type": "trolley"}]
        return engine

    def test_TP1_enable(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "enable", "value": 1})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/enable", 1)]

    def test_TP2_dir(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "dir", "value": 0})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/dir", 0)]

    def test_TP3_speed(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "speed", "value": 0.7})
        assert ctx["sender"].sends[0][2] == "/trolley/speed"
        assert math.isclose(ctx["sender"].sends[0][3], 0.7)
        assert isinstance(ctx["sender"].sends[0][3], float)

    def test_TP4_step(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "step", "value": 2000})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/step", 2000)]

    def test_TP5_stop(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "stop"})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/stop", 0)]

    def test_TP6_home(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "home"})
        assert ctx["sender"].sends == [("10.0.0.2", 9000, "/trolley/home", 0)]

    def test_TP7_position(self, ctx):
        engine = self._setup_engine(ctx)
        engine._fire_trolley_event({"command": "position", "value": 0.5})
        assert ctx["sender"].sends[0][2] == "/trolley/position"
        assert math.isclose(ctx["sender"].sends[0][3], 0.5)
        assert isinstance(ctx["sender"].sends[0][3], float)

    def test_TP8_event_order_at_same_time(self, ctx):
        """`_trolley_events` orders events firing at the same t as
        enable → dir → speed → position → step → stop → home so the
        show reads correctly. Directly test the ordering map."""
        from engine.playback import PlaybackEngine
        order = PlaybackEngine._TROLLEY_EVENT_ORDER
        assert order["enable"] < order["dir"] < order["speed"]
        assert order["speed"] < order["position"] < order["step"]
        assert order["step"] < order["stop"] < order["home"]

    def test_TP9_send_trolley_stop_to_all_devices(self, ctx):
        engine = ctx["engine"]
        engine._devices = [
            {"id": "a", "ip_address": "10.0.0.2", "osc_port": 9000, "type": "trolley"},
            {"id": "b", "ip_address": "10.0.0.20", "osc_port": 9000, "type": "trolley"},
        ]
        engine._send_trolley_stop()
        assert ctx["sender"].sends == [
            ("10.0.0.2", 9000, "/trolley/stop", 0),
            ("10.0.0.20", 9000, "/trolley/stop", 0),
        ]


# --- Docs Quick Test (D1..D5) -----------------------------------------


class TestQuickTest:
    def test_D1_vents_fan_quick_test(self, ctx):
        r = ctx["client"].post("/api/v1/protocol-test/osc", json={
            "device_id": ctx["vents_id"],
            "address": "/vents/fan/1",
            "values": [0.5],
        })
        assert r.status_code == 200
        assert ctx["sender"].sends == [
            ("10.0.0.1", 9000, "/vents/fan/1", 0.5),
        ]

    def test_D2_trolley_speed_quick_test(self, ctx):
        r = ctx["client"].post("/api/v1/protocol-test/osc", json={
            "device_id": ctx["trolley_id"],
            "address": "/trolley/speed",
            "values": [0.3],
        })
        assert r.status_code == 200
        assert ctx["sender"].sends == [
            ("10.0.0.2", 9000, "/trolley/speed", 0.3),
        ]

    def test_D3_vents_address_on_trolley_rejected(self, ctx):
        r = ctx["client"].post("/api/v1/protocol-test/osc", json={
            "device_id": ctx["trolley_id"],
            "address": "/vents/fan/1",
            "values": [0.5],
        })
        assert r.status_code == 400
        assert ctx["sender"].sends == []

    def test_D4_sys_ping_any_device(self, ctx):
        r = ctx["client"].post("/api/v1/protocol-test/osc", json={
            "device_id": ctx["trolley_id"],
            "address": "/sys/ping",
            "values": [9001],
        })
        assert r.status_code == 200
        assert ctx["sender"].sends == [
            ("10.0.0.2", 9000, "/sys/ping", 9001),
        ]

    def test_D5_address_without_leading_slash(self, ctx):
        r = ctx["client"].post("/api/v1/protocol-test/osc", json={
            "device_id": ctx["vents_id"],
            "address": "vents/fan/1",
            "values": [0.5],
        })
        assert r.status_code == 400
        assert ctx["sender"].sends == []


# --- OSC Bridge routing (B1..B6) -------------------------------------


class TestBridgeRouting:
    """Drive OscBridge._handle directly with fake (ip, port) tuples and
    assert the fan-out outputs. Doesn't exercise the UDP server — that's
    python-osc's problem, not ours."""

    @pytest.fixture
    def bridge(self, ctx):
        from engine.osc_bridge import OscBridge
        devices = [
            {"id": "vents-a",   "name": "va",  "ip_address": "10.0.0.1",
             "osc_port": 9000, "type": "vents"},
            {"id": "vents-b",   "name": "vb",  "ip_address": "10.0.0.2",
             "osc_port": 9000, "type": "vents"},
            {"id": "trolley-c", "name": "tc",  "ip_address": "10.0.0.3",
             "osc_port": 9000, "type": "trolley"},
        ]
        b = OscBridge(
            port=0, routing="type-match",
            osc_sender=ctx["sender"], device_provider=lambda: devices,
        )
        return b

    def _out(self, sender):
        """Drop-zero /sys/ping etc aren't sent here; surface just the
        dispatched calls."""
        return sender.sends

    def test_B1_targeted_dispatch_rewrites_address(self, ctx, bridge):
        bridge._handle(("1.1.1.1", 1000), "/to/vents-a/vents/fan/1", 0.5)
        assert ctx["sender"].sends == [
            ("10.0.0.1", 9000, "/vents/fan/1", 0.5),
        ]

    def test_B2_type_match_vents(self, ctx, bridge):
        bridge.set_routing("type-match")
        bridge._handle(("1.1.1.1", 1000), "/vents/fan/1", 0.5)
        ips = {s[0] for s in ctx["sender"].sends}
        assert ips == {"10.0.0.1", "10.0.0.2"}  # both vents, no trolley

    def test_B3_type_match_trolley(self, ctx, bridge):
        bridge.set_routing("type-match")
        bridge._handle(("1.1.1.1", 1000), "/trolley/speed", 0.3)
        ips = {s[0] for s in ctx["sender"].sends}
        assert ips == {"10.0.0.3"}

    def test_B4_type_match_sys_all_devices(self, ctx, bridge):
        bridge.set_routing("type-match")
        bridge._handle(("1.1.1.1", 1000), "/sys/ping", 9001)
        ips = {s[0] for s in ctx["sender"].sends}
        assert ips == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}

    def test_B5_passthrough_fans_out_everywhere(self, ctx, bridge):
        bridge.set_routing("passthrough")
        bridge._handle(("1.1.1.1", 1000), "/custom/anything", 42)
        ips = {s[0] for s in ctx["sender"].sends}
        assert ips == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}

    def test_B6_routing_none_drops(self, ctx, bridge):
        bridge.set_routing("none")
        bridge._handle(("1.1.1.1", 1000), "/vents/fan/1", 0.5)
        assert ctx["sender"].sends == []
