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
    vents._temp_files[:] = [None, None]
    vents.target_temp_c = 25.0
    vents.max_temp_c = 80.0
    vents.min_fan_pct = 20.0
    vents.max_fan_pct = 100.0
    vents.over_temp_fan_pct = 100.0
    vents.mode = "raw"
    vents.state = "idle"
    vents.last_osc_time = 0.0
    vents._shutdown_event.clear()


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

    def test_fan_zero_drops_below_floor(self):
        # 0.0 should resolve to 0% duty (explicit off, not floor)
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_once_with(0.0)

    def test_manual_fan_forces_mode_raw(self):
        vents.mode = "auto"
        vents.handle_fan_1("/vents/fan/1", 0.3)
        assert vents.mode == "raw"


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

    def test_set_fan_zero_still_zero_with_high_floor(self):
        vents.min_fan_pct = 50.0
        vents.handle_fan_1("/vents/fan/1", 0.0)
        # explicit 0.0 always passes through; floor only applies to non-zero requests
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(0.0)

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

    def test_explicit_zero_passes_through_under_max(self):
        vents.max_fan_pct = 50.0
        vents.min_fan_pct = 30.0
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(0.0)


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


class TestPerSensorOverTemp:
    def setup_method(self):
        _reset()
        vents.pwm_fan_1 = MagicMock()
        vents.pwm_fan_2 = MagicMock()
        vents.mode = "auto"
        vents.max_temp_c = 80.0
        vents.over_temp_fan_pct = 100.0

    def _tick_auto(self):
        """Run one auto-loop iteration without spinning the thread."""
        # Inline what _auto_loop does for one tick (mode == "auto").
        # Mirrors controllers/vents.py:_auto_loop.
        with patch.object(vents, "GPIO", _make_gpio()):
            avg = vents._avg_temp()
            if avg is None:
                vents.state = "sensor_error"
                vents._apply_peltier_mask(0)
                vents._set_fan(0, 0.0); vents._set_fan(1, 0.0)
            elif vents._any_temp_over_max():
                vents.state = "over_temp"
                vents._apply_peltier_mask(0)
                fb = vents.over_temp_fan_pct / 100.0
                vents._set_fan(0, fb); vents._set_fan(1, fb)
            else:
                vents.state = "holding"

    def test_one_hot_sensor_trips_interlock(self):
        vents.temp_c[0] = 90.0
        vents.temp_c[1] = 25.0
        # avg = 57.5 < 80 (would not trip on average), but per-sensor must fire
        assert vents._avg_temp() == pytest.approx(57.5)
        assert vents._any_temp_over_max() is True

    def test_over_temp_pins_fans_and_clears_peltiers(self):
        vents.temp_c[0] = 95.0
        vents.temp_c[1] = 20.0
        vents.over_temp_fan_pct = 80.0
        vents.peltier_state[:] = [1, 1, 1]
        self._tick_auto()
        assert vents.state == "over_temp"
        assert vents.peltier_state == [0, 0, 0]
        # Both fans pinned to 80% — under the configured fallback
        vents.pwm_fan_1.ChangeDutyCycle.assert_called_with(80.0)
        vents.pwm_fan_2.ChangeDutyCycle.assert_called_with(80.0)

    def test_no_sensor_over_max_does_not_trip(self):
        vents.temp_c[0] = 79.0
        vents.temp_c[1] = 78.0
        assert vents._any_temp_over_max() is False

    def test_missing_sensor_alone_does_not_trip(self):
        vents.temp_c[0] = None
        vents.temp_c[1] = 20.0
        assert vents._any_temp_over_max() is False


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


class TestModeTarget:
    def setup_method(self):
        _reset()

    def test_mode_accepts_raw(self):
        vents.handle_mode("/vents/mode", "raw")
        assert vents.mode == "raw"

    def test_mode_accepts_auto(self):
        vents.handle_mode("/vents/mode", "auto")
        assert vents.mode == "auto"

    def test_mode_rejects_garbage(self):
        vents.handle_mode("/vents/mode", "banana")
        vents._webhooks.fire.assert_called_once()

    def test_target_sets_celsius(self):
        vents.handle_target("/vents/target", 18.5)
        assert vents.target_temp_c == 18.5


# ── status + describe ────────────────────────────────────────────────────


class TestStatus:
    def setup_method(self):
        _reset()

    def test_status_includes_all_fields(self):
        s = vents.get_status()
        for k in (
            "temp1_c", "temp2_c", "fan1", "fan2", "peltier_mask", "peltier",
            "rpm1A", "rpm1B", "rpm2A", "rpm2B", "target_c", "max_temp_c",
            "min_fan_pct", "max_fan_pct", "over_temp_fan_pct",
            "mode", "state", "sensors_ok",
        ):
            assert k in s

    def test_osc_args_encode_missing_temp_as_neg1(self):
        args = vents.get_status_osc_args()
        # temp1 and temp2 are the first two args; both None → -1.0
        assert args[0] == -1.0
        assert args[1] == -1.0
        # Status payload tail layout: ..., target, mode, state, max_temp_c,
        # min_fan_pct, over_temp_fan_pct, max_fan_pct (max_fan_pct appended
        # at the end so older receivers ignoring extras still parse).
        assert isinstance(args[-6], str)   # mode
        assert isinstance(args[-5], str)   # state
        assert isinstance(args[-4], float) # max_temp_c
        assert isinstance(args[-3], float) # min_fan_pct
        assert isinstance(args[-2], float) # over_temp_fan_pct
        assert isinstance(args[-1], float) # max_fan_pct

    def test_osc_args_include_fan_settings(self):
        vents.min_fan_pct = 35.0
        vents.over_temp_fan_pct = 75.0
        vents.max_fan_pct = 60.0
        args = vents.get_status_osc_args()
        assert args[-3] == 35.0
        assert args[-2] == 75.0
        assert args[-1] == 60.0

    def test_osc_args_encode_present_temp(self):
        vents.temp_c[0] = 22.5
        vents.temp_c[1] = 18.0
        args = vents.get_status_osc_args()
        assert args[0] == 22.5
        assert args[1] == 18.0

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
