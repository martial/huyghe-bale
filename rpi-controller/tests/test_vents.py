"""Tests for the new vents controller (3 Peltier cells + 2 PWM fans + tachos + DS18B20)."""

import time
from unittest.mock import MagicMock, patch

import pytest

from controllers import vents


def _reset():
    """Reset module-level state so each test starts clean."""
    vents._webhooks = MagicMock()
    vents.pwm_fan_1 = None
    vents.pwm_fan_2 = None
    vents.peltier_state[:] = [0, 0, 0]
    vents.fan_duty[:] = [20.0, 20.0]
    vents.tacho_rpm[:] = [0.0, 0.0, 0.0, 0.0]
    vents.tacho_last_t[:] = [0.0, 0.0, 0.0, 0.0]
    vents.temp_c[:] = [None, None]
    vents._probes.clear()
    vents._probe_temps.clear()
    # Keep the controller unlocked by default in tests that are not about
    # probe safety. Specific tests can override via _populate_probes().
    default_probe = "28-000000000001"
    vents._probes[default_probe] = f"/sys/bus/w1/devices/{default_probe}/w1_slave"
    vents._probe_temps[default_probe] = 20.0
    vents.temp_c[0] = 20.0
    vents.probe_hot_id = None
    vents.probe_cold_id = None
    vents.hot_target_c = 25.0
    vents.cold_target_c = 25.0
    vents.active_target = "hot"
    vents.max_temp_c = 80.0
    vents.min_fan_pct = 20.0
    vents.max_fan_pct = 100.0
    vents.over_temp_fan_pct = 100.0
    vents.mode = "raw"
    vents.state = "idle"
    vents.last_osc_time = 0.0
    vents._shutdown_event.clear()


# Test ROM ids — used throughout the dual-setpoint / probe assignment tests.
HOT_ID = "28-aaaaaaaaaaaa"
COLD_ID = "28-bbbbbbbbbbbb"
THIRD_ID = "28-cccccccccccc"


def _populate_probes(temps):
    """Helper: seed _probes and _probe_temps from a {rom_id: temp_c} dict.
    Also refreshes temp_c[0..1] to match the back-compat 2-slot view."""
    vents._probes.clear()
    vents._probe_temps.clear()
    for rom_id, t in temps.items():
        vents._probes[rom_id] = f"/sys/bus/w1/devices/{rom_id}/w1_slave"
        vents._probe_temps[rom_id] = t
    ordered = sorted(vents._probes.keys())
    for i in range(2):
        vents.temp_c[i] = vents._probe_temps.get(ordered[i]) if i < len(ordered) else None


def _assign_both(hot=HOT_ID, cold=COLD_ID):
    vents.probe_hot_id = hot
    vents.probe_cold_id = cold


def _make_gpio():
    g = MagicMock()
    g.BCM = 11
    g.OUT = 0
    g.IN = 1
    g.HIGH = 1
    g.LOW = 0
    g.PUD_UP = 22
    g.FALLING = 32
    return g


# ── setup / cleanup ────────────────────────────────────────────────────────


class TestSetup:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        with patch.object(vents, "GPIO", _make_gpio()):
            vents.cleanup()

    def test_configures_peltier_fan_tacho_pins(self):
        gpio = _make_gpio()
        with patch.object(vents, "GPIO", gpio), \
             patch.object(vents.os, "system", return_value=0), \
             patch.object(vents.glob, "glob", return_value=[]):
            vents.setup(MagicMock())
        # 3 peltier + 2 fan PWM + 4 tacho = 9 GPIO.setup calls
        assert gpio.setup.call_count == 9
        # 2 PWM objects created
        assert gpio.PWM.call_count == 2
        # 4 tacho event-detect registrations
        assert gpio.add_event_detect.call_count == 4


class TestCleanup:
    def setup_method(self):
        _reset()
        self.gpio = _make_gpio()
        self._patch = patch.object(vents, "GPIO", self.gpio)
        self._patch.start()
        with patch.object(vents.os, "system", return_value=0), \
             patch.object(vents.glob, "glob", return_value=[]):
            vents.setup(MagicMock())

    def teardown_method(self):
        self._patch.stop()

    def test_sets_peltiers_low_and_stops_pwm(self):
        vents.cleanup()
        assert any(
            c.args == (vents.PIN_PELTIER_1, 0)
            for c in self.gpio.output.call_args_list
        )
        assert vents.pwm_fan_1.stop.called
        assert vents.pwm_fan_2.stop.called


# ── OSC handlers ──────────────────────────────────────────────────────────


class TestPeltierHandlers:
    def setup_method(self):
        _reset()

    def test_peltier_1_on(self):
        with patch.object(vents, "GPIO", _make_gpio()) as gpio:
            vents.handle_peltier_1("/vents/peltier/1", 1)
            gpio.output.assert_called_with(vents.PIN_PELTIER_1, 1)
            assert vents.peltier_state[0] == 1

    def test_peltier_mask_all(self):
        with patch.object(vents, "GPIO", _make_gpio()):
            vents.handle_peltier_mask("/vents/peltier", 0b101)
            assert vents.peltier_state == [1, 0, 1]

    def test_manual_peltier_forces_mode_raw(self):
        vents.mode = "auto"
        with patch.object(vents, "GPIO", _make_gpio()):
            vents.handle_peltier_1("/vents/peltier/1", 1)
        assert vents.mode == "raw"

    def test_peltier_on_suppressed_when_probe_fault_active(self):
        _populate_probes({HOT_ID: None})
        with patch.object(vents, "GPIO", _make_gpio()) as gpio:
            vents.handle_peltier_1("/vents/peltier/1", 1)
            gpio.output.assert_called_with(vents.PIN_PELTIER_1, 0)
        assert vents.peltier_state[0] == 0

    def test_updates_last_osc_time(self):
        before = time.time()
        with patch.object(vents, "GPIO", _make_gpio()):
            vents.handle_peltier_1("/vents/peltier/1", 1)
        assert vents.last_osc_time >= before

    def test_error_fires_webhook(self):
        with patch.object(vents, "GPIO", _make_gpio()) as gpio:
            gpio.output.side_effect = RuntimeError("pin boom")
            vents.handle_peltier_1("/vents/peltier/1", 1)
        vents._webhooks.fire.assert_called_once()


class TestFanHandlers:
    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()

    def test_fan_1_duty(self):
        vents.handle_fan_1("/vents/fan/1", 0.5)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_once_with(50.0)
        assert vents.fan_duty[0] == 50.0

    def test_fan_2_duty(self):
        vents.handle_fan_2("/vents/fan/2", 1.0)
        vents.pwm_fan_2.ChangeDutyCycle.assert_called_once_with(100.0)

    def test_fan_clamps_high(self):
        vents.handle_fan_1("/vents/fan/1", 2.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_once_with(100.0)

    def test_fan_zero_respects_floor(self):
        # Floor is unconditional: 0.0 command still maps to min_fan_pct.
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_once_with(20.0)

    def test_manual_fan_keeps_auto_mode(self):
        vents.mode = "auto"
        vents.handle_fan_1("/vents/fan/1", 0.3)
        assert vents.mode == "auto"

    def test_fan_override_suppressed_during_over_temp_lock(self):
        _populate_probes({HOT_ID: 95.0})
        vents.max_temp_c = 80.0
        vents.over_temp_fan_pct = 70.0
        vents.handle_fan_1("/vents/fan/1", 0.2)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_once_with(70.0)
        assert vents.fan_duty[0] == 70.0


class TestDynamicMinFanPct:
    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()

    def test_handler_updates_floor_and_persists(self):
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_min_fan_pct("/vents/config/min_fan_pct", 35.0)
        assert vents.min_fan_pct == 35.0
        save.assert_called_once()

    def test_handler_clamps_out_of_range(self):
        with patch.object(vents, "_save_prefs"):
            vents.handle_min_fan_pct("/vents/config/min_fan_pct", 250.0)
        assert vents.min_fan_pct == 100.0
        with patch.object(vents, "_save_prefs"):
            vents.handle_min_fan_pct("/vents/config/min_fan_pct", -5.0)
        assert vents.min_fan_pct == 0.0

    def test_set_fan_respects_dynamic_floor(self):
        vents.min_fan_pct = 40.0
        # 0.1 → raw 10%, but floor 40% kicks in (request was non-zero)
        vents.handle_fan_1("/vents/fan/1", 0.1)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(40.0)

    def test_set_fan_zero_uses_high_floor(self):
        vents.min_fan_pct = 50.0
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(50.0)

    def test_set_fan_above_floor_passes_through(self):
        vents.min_fan_pct = 20.0
        vents.handle_fan_1("/vents/fan/1", 0.7)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(70.0)


class TestMaxFanPct:
    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()

    def test_handler_updates_and_persists(self):
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_max_fan_pct("/vents/config/max_fan_pct", 60.0)
        assert vents.max_fan_pct == 60.0
        save.assert_called_once()

    def test_handler_clamps_out_of_range(self):
        with patch.object(vents, "_save_prefs"):
            vents.handle_max_fan_pct("/vents/config/max_fan_pct", 250.0)
        assert vents.max_fan_pct == 100.0
        with patch.object(vents, "_save_prefs"):
            vents.handle_max_fan_pct("/vents/config/max_fan_pct", -5.0)
        assert vents.max_fan_pct == 0.0

    def test_max_fan_pct_scales_full_command(self):
        vents.max_fan_pct = 50.0
        vents.min_fan_pct = 0.0  # disable floor for clean math
        vents.handle_fan_1("/vents/fan/1", 1.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(50.0)

    def test_max_fan_pct_scales_partial_command(self):
        vents.max_fan_pct = 80.0
        vents.min_fan_pct = 0.0
        # 0.5 × 80% = 40% — confirms scale is a multiplier, not just a ceiling
        vents.handle_fan_1("/vents/fan/1", 0.5)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(40.0)

    def test_floor_overrides_scale_for_tiny_inputs(self):
        vents.max_fan_pct = 80.0
        vents.min_fan_pct = 20.0
        # 0.1 × 80% = 8% → below floor 20% → floor wins
        vents.handle_fan_1("/vents/fan/1", 0.1)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(20.0)

    def test_zero_still_respects_floor_under_max(self):
        vents.max_fan_pct = 50.0
        vents.min_fan_pct = 30.0
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(30.0)


class TestOverTempFanFallback:
    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()

    def test_handler_updates_and_persists(self):
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_over_temp_fan_pct("/vents/config/over_temp_fan_pct", 60.0)
        assert vents.over_temp_fan_pct == 60.0
        save.assert_called_once()


def _tick_auto():
    """Run one /auto loop tick without spinning the thread. Mirrors the
    branches in controllers/vents.py:_auto_loop."""
    with patch.object(vents, "GPIO", _make_gpio()):
        if vents._probe_safety_fault():
            vents.state = "sensor_error"
            vents._apply_peltier_mask(0)
            fb = vents.over_temp_fan_pct / 100.0
            vents._set_fan(0, fb); vents._set_fan(1, fb)
            return
        if any(t is not None and t > vents.max_temp_c for t in vents._probe_temps.values()):
            vents.state = "over_temp"
            vents._apply_peltier_mask(0)
            fb = vents.over_temp_fan_pct / 100.0
            vents._set_fan(0, fb); vents._set_fan(1, fb)
            return
        if vents.mode != "auto":
            vents.state = "idle"
            return
        hot_present = vents.probe_hot_id is not None and vents.probe_hot_id in vents._probes
        cold_present = vents.probe_cold_id is not None and vents.probe_cold_id in vents._probes
        if not hot_present or not cold_present:
            vents.state = "probe_unassigned"
            vents._apply_peltier_mask(0)
            vents._set_fan(0, 0.0); vents._set_fan(1, 0.0)
            return
        t_hot = vents._probe_temps.get(vents.probe_hot_id)
        t_cold = vents._probe_temps.get(vents.probe_cold_id)
        if t_hot is None or t_cold is None:
            vents.state = "sensor_error"
            vents._apply_peltier_mask(0)
            fb = vents.over_temp_fan_pct / 100.0
            vents._set_fan(0, fb); vents._set_fan(1, fb)
            return
        H = vents.VENTS_HYSTERESIS_C
        if vents.active_target == "cold":
            need_on = t_cold > vents.cold_target_c + H
            need_off = t_cold <= vents.cold_target_c - H
        else:
            need_on = t_hot < vents.hot_target_c - H
            need_off = t_hot >= vents.hot_target_c + H
        if need_on:
            vents.state = "heating"
            vents._apply_peltier_mask(0b111)
        elif need_off:
            vents.state = "cooling"
            vents._apply_peltier_mask(0)
        else:
            vents.state = "holding"


class TestPerSensorOverTemp:
    """The over-temp interlock fires on per-sensor max, including for an
    unassigned probe still on the bus. Predates dual setpoints — kept
    because the safety logic is unchanged."""

    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()
        vents.mode = "auto"
        vents.max_temp_c = 80.0
        vents.over_temp_fan_pct = 100.0
        _assign_both()

    def test_one_hot_probe_trips_interlock(self):
        _populate_probes({HOT_ID: 90.0, COLD_ID: 25.0})
        # Even one probe over max trips, regardless of avg.
        assert vents._over_temp_interlock() is True

    def test_unassigned_probe_over_max_still_trips(self):
        # Hot/cold assigned to in-range probes; an unassigned third probe
        # on the bus reads over max → safety still fires.
        _populate_probes({HOT_ID: 25.0, COLD_ID: 20.0, THIRD_ID: 95.0})
        assert vents._over_temp_interlock() is True

    def test_over_temp_pins_fans_and_clears_peltiers(self):
        _populate_probes({HOT_ID: 95.0, COLD_ID: 20.0})
        vents.over_temp_fan_pct = 80.0
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        assert vents.state == "over_temp"
        assert vents.peltier_state == [0, 0, 0]
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(80.0)
        vents.pwm_fan_2.ChangeDutyCycle.assert_called_with(80.0)

    def test_no_sensor_over_max_does_not_trip(self):
        _populate_probes({HOT_ID: 79.0, COLD_ID: 78.0})
        assert vents._over_temp_interlock() is False

    def test_raw_mode_still_enforces_over_temp_lock(self):
        vents.mode = "raw"
        _populate_probes({HOT_ID: 95.0, COLD_ID: 20.0})
        vents.peltier_state[:] = [1, 1, 1]
        vents.over_temp_fan_pct = 80.0
        _tick_auto()
        assert vents.state == "over_temp"
        assert vents.peltier_state == [0, 0, 0]
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(80.0)
        vents.pwm_fan_2.ChangeDutyCycle.assert_called_with(80.0)

    def test_missing_sensor_trips_probe_safety_lock(self):
        _populate_probes({HOT_ID: None, COLD_ID: 20.0})
        assert vents._over_temp_interlock() is False
        assert vents._probe_safety_fault() is True
        assert vents._safety_lock_state() == "sensor_error"

    def test_no_discovered_probe_trips_probe_safety_lock(self):
        _populate_probes({})
        assert vents._probe_safety_fault() is True
        assert vents._safety_lock_state() == "sensor_error"

    def test_abnormal_probe_value_trips_probe_safety_lock(self):
        _populate_probes({HOT_ID: 200.0, COLD_ID: 20.0})
        assert vents._probe_safety_fault() is True
        assert vents._safety_lock_state() == "sensor_error"

    def test_raw_mode_sensor_fault_still_enforces_lock(self):
        vents.mode = "raw"
        _populate_probes({HOT_ID: None, COLD_ID: 20.0})
        vents.peltier_state[:] = [1, 1, 1]
        vents.over_temp_fan_pct = 80.0
        _tick_auto()
        assert vents.state == "sensor_error"
        assert vents.peltier_state == [0, 0, 0]
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(80.0)
        vents.pwm_fan_2.ChangeDutyCycle.assert_called_with(80.0)


class TestPrefsPersistence:
    def setup_method(self):
        _reset()

    def test_save_includes_all_prefs(self, tmp_path):
        vents.max_temp_c = 70.0
        vents.min_fan_pct = 25.5
        vents.max_fan_pct = 60.0
        vents.over_temp_fan_pct = 90.0
        path = tmp_path / "prefs.json"
        with patch.object(vents, "_PREFS_PATH", path):
            vents._save_prefs()
        import json as _json
        data = _json.loads(path.read_text())
        assert data["max_temp_c"] == 70.0
        assert data["min_fan_pct"] == 25.5
        assert data["max_fan_pct"] == 60.0
        assert data["over_temp_fan_pct"] == 90.0

    def test_load_restores_all(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text(
            '{"max_temp_c": 60, "min_fan_pct": 33, "max_fan_pct": 80, "over_temp_fan_pct": 70}'
        )
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.max_temp_c == 60.0
        assert vents.min_fan_pct == 33.0
        assert vents.max_fan_pct == 80.0
        assert vents.over_temp_fan_pct == 70.0

    def test_load_tolerates_missing_new_keys(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text('{"max_temp_c": 65}')
        vents.min_fan_pct = 99.0  # unchanged when key absent
        vents.over_temp_fan_pct = 99.0
        vents.max_fan_pct = 99.0
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.max_temp_c == 65.0
        assert vents.min_fan_pct == 99.0
        assert vents.over_temp_fan_pct == 99.0
        assert vents.max_fan_pct == 99.0

    def test_save_includes_active_target(self, tmp_path):
        vents.active_target = "cold"
        path = tmp_path / "prefs.json"
        with patch.object(vents, "_PREFS_PATH", path):
            vents._save_prefs()
        import json as _json
        data = _json.loads(path.read_text())
        assert data["active_target"] == "cold"

    def test_load_restores_active_target(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text('{"max_temp_c": 80, "active_target": "cold"}')
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.active_target == "cold"

    def test_load_defaults_active_target_when_missing(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text('{"max_temp_c": 80}')
        vents.active_target = "cold"  # pretend in-memory was something else
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        # Missing key keeps in-memory value (forward-compat). Default at fresh
        # install is "hot" (set in module globals).
        assert vents.active_target == "cold"

    def test_load_rejects_garbage_active_target(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text('{"max_temp_c": 80, "active_target": "lukewarm"}')
        vents.active_target = "hot"
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.active_target == "hot"

    def test_load_clamps_below_floor_setpoint_to_15(self, tmp_path):
        # Stale prefs from older firmware (or operator hand-edit) below the
        # 15 °C floor must be pulled up on load.
        path = tmp_path / "prefs.json"
        path.write_text('{"max_temp_c": 80, "hot_target_c": 10, "cold_target_c": 5}')
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.hot_target_c == pytest.approx(15.0)
        assert vents.cold_target_c == pytest.approx(15.0)


class TestModeTarget:
    def setup_method(self):
        _reset()

    def test_mode_accepts_raw(self):
        vents.handle_mode("/vents/mode", "raw")
        assert vents.mode == "raw"

    def test_mode_accepts_auto(self):
        vents.handle_mode("/vents/mode", "auto")
        assert vents.mode == "auto"

    def test_switching_to_auto_does_not_reset_fans(self):
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()
        vents.handle_fan_1("/vents/fan/1", 0.6)
        vents.handle_fan_2("/vents/fan/2", 0.4)
        vents.handle_mode("/vents/mode", "auto")
        assert vents.fan_duty[0] == 60.0
        assert vents.fan_duty[1] == 40.0

    def test_mode_rejects_garbage(self):
        vents.handle_mode("/vents/mode", "banana")
        vents._webhooks.fire.assert_called_once()

    def test_target_alias_routes_to_hot(self):
        # Legacy /vents/target keeps working — sets the hot setpoint and
        # also flips active_target to hot.
        vents.active_target = "cold"
        vents.handle_target("/vents/target", 18.5)
        assert vents.hot_target_c == 18.5
        assert vents.active_target == "hot"

    def test_register_osc_maps_all_target_subaddresses(self):
        """Regression: /vents/target, /vents/target/hot, /vents/target/cold,
        and /vents/target/active must each be wired into the OSC dispatcher
        when register_osc runs."""
        d = MagicMock()
        vents.register_osc(d)
        mapped = {c.args[0] for c in d.map.call_args_list}
        assert "/vents/target" in mapped
        assert "/vents/target/hot" in mapped
        assert "/vents/target/cold" in mapped
        assert "/vents/target/active" in mapped

    def test_target_hot_sets_celsius(self):
        vents.handle_target_hot("/vents/target/hot", 22.0)
        assert vents.hot_target_c == 22.0

    def test_target_cold_sets_celsius(self):
        vents.handle_target_cold("/vents/target/cold", 18.0)
        assert vents.cold_target_c == 18.0

    def test_target_hot_persists(self):
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_target_hot("/vents/target/hot", 24.0)
        save.assert_called_once()

    def test_target_cold_persists(self):
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_target_cold("/vents/target/cold", 18.0)
        save.assert_called_once()

    def test_target_hot_flips_active_to_hot(self):
        vents.active_target = "cold"
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_hot("/vents/target/hot", 24.0)
        assert vents.active_target == "hot"

    def test_target_cold_flips_active_to_cold(self):
        vents.active_target = "hot"
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_cold("/vents/target/cold", 18.0)
        assert vents.active_target == "cold"

    def test_target_active_flips_without_value_change(self):
        vents.hot_target_c = 22.0
        vents.cold_target_c = 19.0
        vents.active_target = "hot"
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_target_active("/vents/target/active", "cold")
        assert vents.active_target == "cold"
        assert vents.hot_target_c == 22.0
        assert vents.cold_target_c == 19.0
        save.assert_called_once()

    def test_target_active_rejects_garbage(self):
        vents.active_target = "hot"
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_active("/vents/target/active", "lukewarm")
        # @_safe captures; active stays put.
        assert vents.active_target == "hot"
        vents._webhooks.fire.assert_called_once()


# ── status + describe ────────────────────────────────────────────────────


class TestStatus:
    def setup_method(self):
        _reset()

    def test_status_includes_all_fields(self):
        s = vents.get_status()
        for k in (
            "temp1_c", "temp2_c", "fan1", "fan2", "peltier_mask", "peltier",
            "rpm1A", "rpm1B", "rpm2A", "rpm2B",
            "target_c", "hot_target_c", "cold_target_c", "active_target",
            "temp_hot_c", "temp_cold_c", "probe_hot_id", "probe_cold_id",
            "probes",
            "max_temp_c", "min_fan_pct", "max_fan_pct", "over_temp_fan_pct",
            "mode", "state", "sensors_ok",
        ):
            assert k in s

    def test_status_target_c_aliases_hot_target(self):
        # Back-compat: legacy `target_c` field mirrors `hot_target_c` so old
        # admin builds keep working unchanged.
        vents.cold_target_c = 10.0
        vents.hot_target_c = 22.5
        s = vents.get_status()
        assert s["target_c"] == 22.5
        assert s["hot_target_c"] == 22.5

    def test_status_probes_lists_discovered_ids_with_temps(self):
        _populate_probes({HOT_ID: 24.0, THIRD_ID: 26.5})
        s = vents.get_status()
        ids = [p["id"] for p in s["probes"]]
        assert ids == sorted([HOT_ID, THIRD_ID])
        temps = {p["id"]: p["temp_c"] for p in s["probes"]}
        assert temps[HOT_ID] == 24.0
        assert temps[THIRD_ID] == 26.5

    def test_status_temp_hot_cold_resolve_via_probe_ids(self):
        _assign_both()
        _populate_probes({HOT_ID: 28.0, COLD_ID: 18.0})
        s = vents.get_status()
        assert s["temp_hot_c"] == 28.0
        assert s["temp_cold_c"] == 18.0
        assert s["probe_hot_id"] == HOT_ID
        assert s["probe_cold_id"] == COLD_ID

    def test_osc_args_encode_missing_temp_as_neg1(self):
        # All 4 nullable temp fields (temp1, temp2, temp_hot_c, temp_cold_c)
        # encode to -1.0 when missing.
        vents._probes.clear()
        vents._probe_temps.clear()
        vents.temp_c[:] = [None, None]
        args = vents.get_status_osc_args()
        assert args[0] == -1.0    # temp1_c
        assert args[1] == -1.0    # temp2_c
        assert args[16] == -1.0   # temp_hot_c
        assert args[17] == -1.0   # temp_cold_c
        # Tail layout (positions 16-19) is the dual-setpoint addition.
        assert isinstance(args[18], float)  # hot_target_c
        assert isinstance(args[19], float)  # cold_target_c

    def test_osc_args_layout_positions(self):
        # Spot-check critical positions used by admin's _VENTS_OPTIONAL_STATUS_FIELDS.
        vents.cold_target_c = 18.0
        vents.hot_target_c = 25.0
        vents.active_target = "cold"
        vents.max_temp_c = 80.0
        vents.min_fan_pct = 35.0
        vents.over_temp_fan_pct = 75.0
        vents.max_fan_pct = 60.0
        args = vents.get_status_osc_args()
        assert len(args) == 21
        assert args[10] == "raw"             # mode
        assert args[11] == "idle"            # state
        assert args[12] == 80.0              # max_temp_c
        assert args[13] == 35.0              # min_fan_pct
        assert args[14] == 75.0              # over_temp_fan_pct
        assert args[15] == 60.0              # max_fan_pct
        assert args[18] == 25.0              # hot_target_c
        assert args[19] == 18.0              # cold_target_c
        assert args[20] == "cold"            # active_target

    def test_osc_args_encode_present_temp(self):
        # Populate via the canonical path: _probes + _probe_temps. The
        # temp_c[] back-compat view is rebuilt by _populate_probes helper.
        _populate_probes({HOT_ID: 22.5, COLD_ID: 18.0})
        args = vents.get_status_osc_args()
        # sorted(_probes) → temp1 = HOT_ID's reading (sorted alphabetically),
        # which lands in args[0]; temp2 in args[1].
        assert args[0] == 22.5
        assert args[1] == 18.0

    def test_osc_args_include_temp_hot_cold_when_assigned(self):
        _assign_both()
        _populate_probes({HOT_ID: 30.0, COLD_ID: 16.0})
        args = vents.get_status_osc_args()
        assert args[16] == 30.0
        assert args[17] == 16.0

    def test_peltier_mask_reflects_state(self):
        vents.peltier_state[:] = [1, 0, 1]
        assert vents.get_status()["peltier_mask"] == 0b101


class TestHttpTest:
    def setup_method(self):
        _reset()

    def test_peltier_via_http(self):
        with patch.object(vents, "GPIO", _make_gpio()):
            r = vents.handle_http_test({"command": "peltier", "index": 1, "value": 1})
        assert r["ok"] is True
        assert r["peltier"][0] == 1

    def test_fan_via_http(self):
        vents.pwm_fan_1 = MagicMock()
        r = vents.handle_http_test({"command": "fan", "index": 1, "value": 0.75})
        assert r["ok"] is True
        assert r["fan1"] == 0.75

    def test_target_via_http(self):
        r = vents.handle_http_test({"command": "target", "value": 21.5})
        assert r["ok"] is True
        assert r["target_c"] == 21.5

    def test_max_temp_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "max_temp", "value": 30.0})
        assert r["ok"] is True
        assert r["max_temp_c"] == 30.0

    def test_min_fan_pct_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "min_fan_pct", "value": 25.0})
        assert r["ok"] is True
        assert r["min_fan_pct"] == 25.0

    def test_max_fan_pct_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "max_fan_pct", "value": 70.0})
        assert r["ok"] is True
        assert r["max_fan_pct"] == 70.0

    def test_over_temp_fan_pct_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "over_temp_fan_pct", "value": 75.0})
        assert r["ok"] is True
        assert r["over_temp_fan_pct"] == 75.0

    def test_unknown_command(self):
        r = vents.handle_http_test({"command": "teleport"})
        assert r["ok"] is False

    def test_target_hot_via_http(self):
        r = vents.handle_http_test({"command": "target_hot", "value": 22.0})
        assert r["ok"] is True
        assert r["hot_target_c"] == 22.0
        assert r["active_target"] == "hot"

    def test_target_cold_via_http(self):
        r = vents.handle_http_test({"command": "target_cold", "value": 18.0})
        assert r["ok"] is True
        assert r["cold_target_c"] == 18.0
        assert r["active_target"] == "cold"

    def test_target_active_via_http(self):
        vents.hot_target_c = 22.0
        vents.cold_target_c = 19.0
        vents.active_target = "hot"
        r = vents.handle_http_test({"command": "target_active", "value": "cold"})
        assert r["ok"] is True
        assert r["active_target"] == "cold"
        assert r["hot_target_c"] == 22.0
        assert r["cold_target_c"] == 19.0

    def test_probe_assign_hot_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "probe_assign_hot", "value": HOT_ID})
        assert r["ok"] is True
        assert r["probe_hot_id"] == HOT_ID

    def test_probe_assign_cold_via_http(self):
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "probe_assign_cold", "value": COLD_ID})
        assert r["ok"] is True
        assert r["probe_cold_id"] == COLD_ID

    def test_probe_clear_via_http(self):
        vents.probe_hot_id = HOT_ID
        vents.probe_cold_id = COLD_ID
        with patch.object(vents, "_save_prefs"):
            r = vents.handle_http_test({"command": "probe_clear", "value": "both"})
        assert r["ok"] is True
        assert r["probe_hot_id"] is None
        assert r["probe_cold_id"] is None

    def test_snapshot_returns_status_no_op(self):
        # Snapshot must not change any state — admin uses it to read probes.
        vents.peltier_state[:] = [0, 0, 0]
        r = vents.handle_http_test({"command": "snapshot"})
        assert r["ok"] is True
        assert "probes" in r
        assert vents.peltier_state == [0, 0, 0]


class TestDescribe:
    def test_describe(self):
        _reset()
        d = vents.describe()
        assert d["controller"] == "vents"
        assert "pins" in d
        assert d["pins"]["peltier"] == list(vents.PELTIER_PINS)


# ── DS18B20 parsing ──────────────────────────────────────────────────────


class TestDS18B20Parser:
    def test_valid_reading(self, tmp_path):
        p = tmp_path / "w1_slave"
        p.write_text(
            "aa bb cc dd ee ff : crc=aa YES\n"
            "aa bb cc dd ee ff t=23125\n"
        )
        assert vents._read_ds18b20(str(p)) == pytest.approx(23.125)

    def test_invalid_crc(self, tmp_path):
        p = tmp_path / "w1_slave"
        p.write_text(
            "aa bb cc dd ee ff : crc=aa NO\n"
            "aa bb cc dd ee ff t=23125\n"
        )
        assert vents._read_ds18b20(str(p)) is None

    def test_missing_file(self):
        assert vents._read_ds18b20("/nope/missing") is None


# ── dual-setpoint auto loop ──────────────────────────────────────────────


class TestActiveTargetAuto:
    """Single-active-side bang-bang. The active side's probe is the only
    driver of the Peltier mask; the inactive side's value is irrelevant to
    regulation (but its probe still trips safety branches). _tick_auto
    inlines the loop body so we don't spin a thread; the production loop's
    branch ordering is mirrored exactly."""

    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()
        vents.mode = "auto"
        vents.max_temp_c = 80.0
        vents.hot_target_c = 25.0
        vents.cold_target_c = 18.0
        vents.over_temp_fan_pct = 100.0

    # ── safety / precondition branches (same regardless of active side) ──

    def test_probe_unassigned_when_ids_null(self):
        # No assignment + probes discovered → still unassigned.
        _populate_probes({HOT_ID: 22.0, COLD_ID: 19.0})
        _tick_auto()
        assert vents.state == "probe_unassigned"
        assert vents.peltier_state == [0, 0, 0]

    def test_assigned_id_missing_with_no_discovered_probe_is_sensor_error(self):
        _assign_both()
        _populate_probes({})
        _tick_auto()
        assert vents.state == "sensor_error"

    def test_probe_unassigned_when_only_one_role_assigned(self):
        # Both probes still required for auto, even though only one regulates.
        vents.probe_hot_id = HOT_ID
        vents.probe_cold_id = None
        _populate_probes({HOT_ID: 22.0})
        _tick_auto()
        assert vents.state == "probe_unassigned"

    def test_over_temp_supersedes_active_target_rule(self):
        _assign_both()
        _populate_probes({HOT_ID: 25.0, COLD_ID: 18.0, THIRD_ID: 95.0})
        _tick_auto()
        assert vents.state == "over_temp"
        assert vents.peltier_state == [0, 0, 0]

    def test_sensor_error_when_assigned_probe_reads_none(self):
        _assign_both()
        _populate_probes({HOT_ID: 25.0, COLD_ID: None})
        _tick_auto()
        assert vents.state == "sensor_error"
        assert vents.peltier_state == [0, 0, 0]

    def test_mode_raw_returns_idle(self):
        _assign_both()
        _populate_probes({HOT_ID: 22.0, COLD_ID: 22.0})
        vents.mode = "raw"
        _tick_auto()
        assert vents.state == "idle"

    # ── active = hot ─────────────────────────────────────────────────────

    def test_active_hot_below_band_drives_on(self):
        _assign_both()
        vents.active_target = "hot"
        # hot too cool by >H; cold value is intentionally also out-of-band but
        # MUST be ignored — only hot drives the mask now.
        _populate_probes({HOT_ID: 22.0, COLD_ID: 30.0})
        _tick_auto()
        assert vents.state == "heating"
        assert vents.peltier_state == [1, 1, 1]

    def test_active_hot_above_band_drives_off(self):
        _assign_both()
        vents.active_target = "hot"
        # hot above hot_target+H; cold deliberately too warm — but ignored.
        _populate_probes({HOT_ID: 26.0, COLD_ID: 22.0})
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        assert vents.state == "cooling"
        assert vents.peltier_state == [0, 0, 0]

    def test_active_hot_in_deadband_holds_previous_mask(self):
        _assign_both()
        vents.active_target = "hot"
        _populate_probes({HOT_ID: 24.8, COLD_ID: 30.0})  # hot in deadband; cold ignored
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        assert vents.state == "holding"
        assert vents.peltier_state == [1, 1, 1]

    def test_active_hot_ignores_cold_probe_value(self):
        # Cold probe at any value cannot affect the regulation decision when
        # active=hot. Both ON-side and OFF-side checks pin to the hot probe.
        _assign_both()
        vents.active_target = "hot"
        _populate_probes({HOT_ID: 26.0, COLD_ID: 50.0})
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        # Old OR rule would have stayed in heating (cold too warm). New rule:
        # hot above setpoint+H ⇒ cooling.
        assert vents.state == "cooling"
        assert vents.peltier_state == [0, 0, 0]

    # ── active = cold ────────────────────────────────────────────────────

    def test_active_cold_above_band_drives_on(self):
        _assign_both()
        vents.active_target = "cold"
        # cold too warm by >H; hot value irrelevant.
        _populate_probes({HOT_ID: 22.0, COLD_ID: 22.0})
        _tick_auto()
        assert vents.state == "heating"
        assert vents.peltier_state == [1, 1, 1]

    def test_active_cold_below_band_drives_off(self):
        _assign_both()
        vents.active_target = "cold"
        _populate_probes({HOT_ID: 22.0, COLD_ID: 17.0})  # hot ignored
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        assert vents.state == "cooling"
        assert vents.peltier_state == [0, 0, 0]

    def test_active_cold_in_deadband_holds_previous_mask(self):
        _assign_both()
        vents.active_target = "cold"
        _populate_probes({HOT_ID: 22.0, COLD_ID: 18.2})  # cold in deadband
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        assert vents.state == "holding"
        assert vents.peltier_state == [1, 1, 1]

    def test_active_cold_ignores_hot_probe_value(self):
        _assign_both()
        vents.active_target = "cold"
        _populate_probes({HOT_ID: 22.0, COLD_ID: 17.0})
        vents.peltier_state[:] = [1, 1, 1]
        _tick_auto()
        # Old OR rule: hot below setpoint−H ⇒ would stay heating. New rule:
        # cold below setpoint−H ⇒ cooling.
        assert vents.state == "cooling"
        assert vents.peltier_state == [0, 0, 0]


# ── cross-clamp invariants ───────────────────────────────────────────────


class TestSetpointClamps:
    """Remaining clamp invariants after the cold-vs-hot rule was dropped:
      (1) hot_target + H + margin < max_temp_c   (safety ceiling)
      (2) hot_target  >= _TARGET_MIN_C            (operator floor, default 15°C)
      (3) cold_target >= _TARGET_MIN_C            (operator floor)
    Always pulls values toward valid range; never raises max_temp_c.
    """

    def setup_method(self):
        _reset()

    def test_hot_target_clamps_below_max_minus_H_minus_margin(self):
        vents.max_temp_c = 30.0
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_hot("/vents/target/hot", 35.0)  # > max
        # ceiling = 30 - 0.5 - 0.05 = 29.45
        assert vents.hot_target_c == pytest.approx(29.45)

    def test_lowering_max_temp_pulls_hot_down(self):
        vents.hot_target_c = 60.0
        vents.cold_target_c = 50.0
        vents._set_max_temp_c(40.0)
        # hot drops to 40 - 0.55 = 39.45; cold is independent and untouched.
        assert vents.hot_target_c == pytest.approx(39.45)
        assert vents.cold_target_c == 50.0

    def test_hot_target_clamped_up_to_15_floor(self):
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_hot("/vents/target/hot", 10.0)
        assert vents.hot_target_c == pytest.approx(15.0)

    def test_cold_target_clamped_up_to_15_floor(self):
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_cold("/vents/target/cold", 5.0)
        assert vents.cold_target_c == pytest.approx(15.0)

    def test_cold_target_independent_of_hot(self):
        # New behavior: cold can be anywhere ≥ 15, regardless of where hot is.
        # The OR-rule deadband requirement is gone.
        vents.hot_target_c = 20.0
        with patch.object(vents, "_save_prefs"):
            vents.handle_target_cold("/vents/target/cold", 30.0)
        assert vents.cold_target_c == 30.0
        assert vents.hot_target_c == 20.0  # untouched


# ── probe assignment ─────────────────────────────────────────────────────


class TestProbeAssignment:
    def setup_method(self):
        _reset()

    def test_assign_hot_persists(self):
        _populate_probes({HOT_ID: 22.0})
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_probe_assign_hot("/vents/probe/assign_hot", HOT_ID)
        assert vents.probe_hot_id == HOT_ID
        save.assert_called_once()

    def test_assign_cold_persists(self):
        _populate_probes({COLD_ID: 18.0})
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_probe_assign_cold("/vents/probe/assign_cold", COLD_ID)
        assert vents.probe_cold_id == COLD_ID
        save.assert_called_once()

    def test_assign_same_id_to_both_roles_rejected(self):
        # Hot already assigned to HOT_ID; assigning the same id as cold must
        # raise (caught by @_safe → fires webhooks.fire("error", ...)).
        vents.probe_hot_id = HOT_ID
        with patch.object(vents, "_save_prefs"):
            vents.handle_probe_assign_cold("/vents/probe/assign_cold", HOT_ID)
        # @_safe captures the exception; cold remains unset.
        assert vents.probe_cold_id is None
        vents._webhooks.fire.assert_called_once()

    def test_assign_invalid_rom_id_rejected(self):
        with patch.object(vents, "_save_prefs"):
            vents.handle_probe_assign_hot("/vents/probe/assign_hot", "not-a-rom-id")
        assert vents.probe_hot_id is None
        vents._webhooks.fire.assert_called_once()

    def test_clear_both(self):
        vents.probe_hot_id = HOT_ID
        vents.probe_cold_id = COLD_ID
        with patch.object(vents, "_save_prefs"):
            vents.handle_probe_clear("/vents/probe/clear", "both")
        assert vents.probe_hot_id is None
        assert vents.probe_cold_id is None

    def test_clear_only_hot(self):
        vents.probe_hot_id = HOT_ID
        vents.probe_cold_id = COLD_ID
        with patch.object(vents, "_save_prefs"):
            vents.handle_probe_clear("/vents/probe/clear", "hot")
        assert vents.probe_hot_id is None
        assert vents.probe_cold_id == COLD_ID

    def test_clear_invalid_value_rejected(self):
        vents.probe_hot_id = HOT_ID
        with patch.object(vents, "_save_prefs"):
            vents.handle_probe_clear("/vents/probe/clear", "garbage")
        # @_safe captures; assignment unchanged.
        assert vents.probe_hot_id == HOT_ID
        vents._webhooks.fire.assert_called_once()

    def test_assign_id_not_in_probes_persists_with_warning(self):
        # Operator may configure before the probe is wired in.
        _populate_probes({})  # nothing discovered
        with patch.object(vents, "_save_prefs") as save:
            vents.handle_probe_assign_hot("/vents/probe/assign_hot", HOT_ID)
        assert vents.probe_hot_id == HOT_ID  # persisted anyway
        save.assert_called_once()


# ── probe discovery ──────────────────────────────────────────────────────


class TestProbeDiscovery:
    def setup_method(self):
        _reset()

    def test_discover_keys_by_rom_id(self, monkeypatch):
        # Stub glob to return two fake DS18B20 device folders.
        fake = ["/sys/bus/w1/devices/28-aaaaaaaaaaaa",
                "/sys/bus/w1/devices/28-bbbbbbbbbbbb"]
        monkeypatch.setattr(vents.glob, "glob", lambda pattern: fake)
        vents._discover_sensors()
        assert set(vents._probes.keys()) == {"28-aaaaaaaaaaaa", "28-bbbbbbbbbbbb"}
        assert vents._probes["28-aaaaaaaaaaaa"].endswith("/w1_slave")

    def test_rediscovery_drops_stale_temps(self, monkeypatch):
        # First scan: two probes present, both with cached temps.
        fake = ["/sys/bus/w1/devices/28-aaaaaaaaaaaa",
                "/sys/bus/w1/devices/28-bbbbbbbbbbbb"]
        monkeypatch.setattr(vents.glob, "glob", lambda pattern: fake)
        vents._discover_sensors()
        vents._probe_temps["28-aaaaaaaaaaaa"] = 24.0
        vents._probe_temps["28-bbbbbbbbbbbb"] = 19.0
        # Second scan: only one probe still on the bus.
        monkeypatch.setattr(
            vents.glob, "glob",
            lambda pattern: ["/sys/bus/w1/devices/28-aaaaaaaaaaaa"],
        )
        vents._discover_sensors()
        assert "28-bbbbbbbbbbbb" not in vents._probe_temps
        assert vents._probe_temps["28-aaaaaaaaaaaa"] == 24.0  # surviving probe untouched

    def test_get_status_includes_probes_array(self):
        _populate_probes({HOT_ID: 24.0, COLD_ID: 18.5})
        s = vents.get_status()
        assert len(s["probes"]) == 2
        # sorted by id
        assert s["probes"][0]["id"] < s["probes"][1]["id"]


# ── prefs migration / round-trip ─────────────────────────────────────────


class TestPrefsMigrationAndRoundTrip:
    def setup_method(self):
        _reset()

    def test_legacy_target_temp_c_migrates_to_both(self, tmp_path):
        # Legacy single setpoint seeds both targets identically. The cold-vs-hot
        # cross-clamp is gone, so the values stay equal — operator splits them
        # deliberately later via /vents/target/{hot,cold}.
        path = tmp_path / "prefs.json"
        path.write_text(
            '{"target_temp_c": 22.5, "max_temp_c": 80.0}'
        )
        vents.hot_target_c = 99.0
        vents.cold_target_c = 99.0
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.hot_target_c == 22.5
        assert vents.cold_target_c == 22.5

    def test_legacy_target_below_floor_lifts_both_to_15(self, tmp_path):
        # Legacy below-floor value is clamped up to 15 by _PREFS_RANGES.
        path = tmp_path / "prefs.json"
        path.write_text(
            '{"target_temp_c": 8.0, "max_temp_c": 80.0}'
        )
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.hot_target_c == pytest.approx(15.0)
        assert vents.cold_target_c == pytest.approx(15.0)

    def test_save_includes_dual_setpoints_and_probe_ids(self, tmp_path):
        vents.hot_target_c = 28.0
        vents.cold_target_c = 18.0
        vents.probe_hot_id = HOT_ID
        vents.probe_cold_id = COLD_ID
        path = tmp_path / "prefs.json"
        with patch.object(vents, "_PREFS_PATH", path):
            vents._save_prefs()
        import json as _json
        data = _json.loads(path.read_text())
        assert data["hot_target_c"] == 28.0
        assert data["cold_target_c"] == 18.0
        assert data["probe_hot_id"] == HOT_ID
        assert data["probe_cold_id"] == COLD_ID

    def test_load_restores_probe_ids(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text(
            f'{{"max_temp_c": 80, "hot_target_c": 25, "cold_target_c": 18,'
            f' "probe_hot_id": "{HOT_ID}", "probe_cold_id": "{COLD_ID}"}}'
        )
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.probe_hot_id == HOT_ID
        assert vents.probe_cold_id == COLD_ID

    def test_load_ignores_malformed_probe_id(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text(
            '{"max_temp_c": 80, "probe_hot_id": "garbage", "probe_cold_id": null}'
        )
        with patch.object(vents, "_PREFS_PATH", path):
            vents._load_prefs()
        assert vents.probe_hot_id is None
        assert vents.probe_cold_id is None
