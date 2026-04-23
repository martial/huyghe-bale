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
    vents.fan_duty[:] = [vents.VENTS_FAN_PWM_MIN_PCT, vents.VENTS_FAN_PWM_MIN_PCT] \
        if hasattr(vents, "VENTS_FAN_PWM_MIN_PCT") else [20.0, 20.0]
    vents.tacho_rpm[:] = [0.0, 0.0, 0.0, 0.0]
    vents.tacho_last_t[:] = [0.0, 0.0, 0.0, 0.0]
    vents.temp_c[:] = [None, None]
    vents._temp_files[:] = [None, None]
    vents.target_temp_c = 25.0
    vents.max_temp_c = 80.0
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
            "rpm1A", "rpm1B", "rpm2A", "rpm2B", "target_c", "max_temp_c", "mode", "state",
            "sensors_ok",
        ):
            assert k in s

    def test_osc_args_encode_missing_temp_as_neg1(self):
        args = vents.get_status_osc_args()
        # temp1 and temp2 are the first two args; both None → -1.0
        assert args[0] == -1.0
        assert args[1] == -1.0
        assert isinstance(args[-3], str)
        assert isinstance(args[-2], str)
        assert isinstance(args[-1], float)

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
