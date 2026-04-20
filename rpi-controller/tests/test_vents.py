"""Tests for controllers.vents — GPIO/PWM/OSC handler logic."""

import time
from unittest.mock import MagicMock, patch

import pytest

from controllers import vents
from controllers.vents import clamp, handle_a, handle_b, setup, cleanup


class TestClamp:
    def test_within_range(self):
        assert clamp(0.5) == 0.5

    def test_lower_bound(self):
        assert clamp(-1.0) == 0.0

    def test_upper_bound(self):
        assert clamp(2.0) == 1.0

    def test_exact_zero(self):
        assert clamp(0.0) == 0.0

    def test_exact_one(self):
        assert clamp(1.0) == 1.0

    def test_custom_range(self):
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(15, 0, 10) == 10


class TestHandleA:
    def setup_method(self):
        self.mock_pwm = MagicMock()
        vents.pwm_a = self.mock_pwm
        vents._webhooks = MagicMock()
        vents.last_osc_time = 0.0

    def test_sets_duty_cycle(self):
        handle_a("/gpio/a", 0.5)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(50.0)

    def test_clamps_high_value(self):
        handle_a("/gpio/a", 1.5)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(100.0)

    def test_clamps_negative_value(self):
        handle_a("/gpio/a", -0.5)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(0.0)

    def test_zero_value(self):
        handle_a("/gpio/a", 0.0)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(0.0)

    def test_no_args_does_nothing(self):
        handle_a("/gpio/a")
        self.mock_pwm.ChangeDutyCycle.assert_not_called()

    def test_updates_last_osc_time(self):
        before = time.time()
        handle_a("/gpio/a", 0.5)
        assert vents.last_osc_time >= before

    def test_error_fires_webhook(self):
        self.mock_pwm.ChangeDutyCycle.side_effect = RuntimeError("pwm fail")
        handle_a("/gpio/a", 0.5)
        vents._webhooks.fire.assert_called_once()
        args = vents._webhooks.fire.call_args
        assert args[0][0] == "error"
        assert "osc_handler" in args[0][1]["source"]


class TestHandleB:
    def setup_method(self):
        self.mock_pwm = MagicMock()
        vents.pwm_b = self.mock_pwm
        vents._webhooks = MagicMock()
        vents.last_osc_time = 0.0

    def test_sets_duty_cycle(self):
        handle_b("/gpio/b", 0.75)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(75.0)

    def test_no_args_does_nothing(self):
        handle_b("/gpio/b")
        self.mock_pwm.ChangeDutyCycle.assert_not_called()

    def test_error_fires_webhook(self):
        self.mock_pwm.ChangeDutyCycle.side_effect = RuntimeError("pwm fail")
        handle_b("/gpio/b", 0.5)
        vents._webhooks.fire.assert_called_once()


class TestSetup:
    def test_initializes_pwm(self):
        mock_pwm = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = mock_pwm
        vents.pwm_a = None
        vents.pwm_b = None
        with patch.object(vents, "GPIO", mock_gpio):
            setup(MagicMock())
        assert mock_gpio.setmode.called
        assert mock_gpio.PWM.call_count == 2
        assert mock_pwm.start.call_count == 2

    def test_sets_direction_pins(self):
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = MagicMock()
        with patch.object(vents, "GPIO", mock_gpio):
            setup(MagicMock())
        # 4 direction + 2 enable pins
        assert mock_gpio.setup.call_count == 6
        # 4 direction pin outputs
        assert mock_gpio.output.call_count == 4


class TestCleanup:
    def setup_method(self):
        vents.pwm_a = MagicMock()
        vents.pwm_b = MagicMock()

    def test_zeros_and_stops_pwm(self):
        with patch.object(vents, "GPIO", MagicMock()):
            cleanup()
        vents.pwm_a.ChangeDutyCycle.assert_called_once_with(0)
        vents.pwm_a.stop.assert_called_once()
        vents.pwm_b.ChangeDutyCycle.assert_called_once_with(0)
        vents.pwm_b.stop.assert_called_once()

    def test_handles_none_pwm(self):
        vents.pwm_a = None
        vents.pwm_b = None
        with patch.object(vents, "GPIO", MagicMock()):
            cleanup()  # must not crash


class TestHttpTest:
    def setup_method(self):
        vents.pwm_a = MagicMock()
        vents.pwm_b = MagicMock()

    def test_returns_ok_with_duties(self):
        with patch.object(vents, "GPIO", MagicMock()):
            result = vents.handle_http_test({"value_a": 0.25, "value_b": 0.75})
        assert result["ok"] is True
        assert result["duty_a"] == 25.0
        assert result["duty_b"] == 75.0
        vents.pwm_a.ChangeDutyCycle.assert_called_once_with(25.0)
        vents.pwm_b.ChangeDutyCycle.assert_called_once_with(75.0)

    def test_clamps(self):
        with patch.object(vents, "GPIO", MagicMock()):
            result = vents.handle_http_test({"value_a": 2.0, "value_b": -1.0})
        assert result["duty_a"] == 100.0
        assert result["duty_b"] == 0.0


class TestDescribe:
    def test_returns_controller_name(self):
        d = vents.describe()
        assert d["controller"] == "vents"
        assert "channels" in d
