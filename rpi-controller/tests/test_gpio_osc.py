"""Tests for gpio_osc module.

RPi.GPIO and pythonosc are mocked via conftest.py so these tests
run on macOS / CI without hardware.
"""

import sys
import time

import pytest
from unittest.mock import MagicMock, patch, call

import gpio_osc
from gpio_osc import clamp, handle_a, handle_b, handle_ping, cleanup, setup_gpio, main


# ── clamp ────────────────────────────────────────────────────────────


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


# ── handle_a ─────────────────────────────────────────────────────────


class TestHandleA:
    def setup_method(self):
        self.mock_pwm = MagicMock()
        gpio_osc.pwm_a = self.mock_pwm
        gpio_osc.webhooks = MagicMock()
        gpio_osc.last_osc_time = 0.0

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
        assert gpio_osc.last_osc_time >= before

    def test_error_fires_webhook(self):
        self.mock_pwm.ChangeDutyCycle.side_effect = RuntimeError("pwm fail")
        handle_a("/gpio/a", 0.5)
        gpio_osc.webhooks.fire.assert_called_once()
        args = gpio_osc.webhooks.fire.call_args
        assert args[0][0] == "error"
        assert "osc_handler" in args[0][1]["source"]


# ── handle_b ─────────────────────────────────────────────────────────


class TestHandleB:
    def setup_method(self):
        self.mock_pwm = MagicMock()
        gpio_osc.pwm_b = self.mock_pwm
        gpio_osc.webhooks = MagicMock()
        gpio_osc.last_osc_time = 0.0

    def test_sets_duty_cycle(self):
        handle_b("/gpio/b", 0.75)
        self.mock_pwm.ChangeDutyCycle.assert_called_once_with(75.0)

    def test_no_args_does_nothing(self):
        handle_b("/gpio/b")
        self.mock_pwm.ChangeDutyCycle.assert_not_called()

    def test_error_fires_webhook(self):
        self.mock_pwm.ChangeDutyCycle.side_effect = RuntimeError("pwm fail")
        handle_b("/gpio/b", 0.5)
        gpio_osc.webhooks.fire.assert_called_once()


# ── handle_ping ──────────────────────────────────────────────────────


class TestHandlePing:
    def setup_method(self):
        gpio_osc.webhooks = MagicMock()

    def test_no_args_does_nothing(self):
        handle_ping(("192.168.1.1", 12345), "/sys/ping")
        # No exception, no webhook fire

    @patch("gpio_osc.SimpleUDPClient")
    def test_sends_pong(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        handle_ping(("192.168.1.10", 50000), "/sys/ping", 8000)
        mock_client_cls.assert_called_once_with("192.168.1.10", 8000)
        mock_client.send_message.assert_called_once_with("/sys/pong", "192.168.1.10")

    def test_error_fires_webhook(self):
        # Pass a non-integer port to trigger error
        handle_ping(("192.168.1.1", 12345), "/sys/ping", "not_a_port")
        gpio_osc.webhooks.fire.assert_called_once()
        assert gpio_osc.webhooks.fire.call_args[0][0] == "error"


# ── cleanup ──────────────────────────────────────────────────────────


class TestCleanup:
    def setup_method(self):
        gpio_osc.shutdown_event.clear()
        gpio_osc.pwm_a = MagicMock()
        gpio_osc.pwm_b = MagicMock()
        gpio_osc.webhooks = MagicMock()

    def test_zeros_and_stops_pwm(self):
        with pytest.raises(SystemExit):
            cleanup()
        gpio_osc.pwm_a.ChangeDutyCycle.assert_called_once_with(0)
        gpio_osc.pwm_a.stop.assert_called_once()
        gpio_osc.pwm_b.ChangeDutyCycle.assert_called_once_with(0)
        gpio_osc.pwm_b.stop.assert_called_once()

    def test_fires_stop_webhook(self):
        with pytest.raises(SystemExit):
            cleanup()
        gpio_osc.webhooks.fire.assert_called_once_with("stop")

    def test_idempotent_second_call_is_noop(self):
        with pytest.raises(SystemExit):
            cleanup()
        # Second call should return immediately (shutdown_event already set)
        cleanup()  # no SystemExit, no double-stop
        # PWM stop should only be called once
        gpio_osc.pwm_a.stop.assert_called_once()

    def test_handles_none_pwm(self):
        gpio_osc.pwm_a = None
        gpio_osc.pwm_b = None
        with pytest.raises(SystemExit):
            cleanup()
        # Should not crash


# ── setup_gpio ───────────────────────────────────────────────────────


class TestSetupGpio:
    def test_initializes_pwm(self):
        mock_pwm = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = mock_pwm
        gpio_osc.pwm_a = None
        gpio_osc.pwm_b = None
        with patch.object(gpio_osc, "GPIO", mock_gpio):
            setup_gpio()
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
        with patch.object(gpio_osc, "GPIO", mock_gpio):
            setup_gpio()
        # Should set up 6 pins total (4 direction + 2 enable)
        assert mock_gpio.setup.call_count == 6
        # Should output on 4 direction pins
        assert mock_gpio.output.call_count == 4


# ── main() resilience — GPIO, OSC port, crash hook, no internet ─────


class TestMainGpioFailure:
    """GPIO hardware missing or broken at startup."""

    def test_gpio_init_failure_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.setmode.side_effect = RuntimeError("No GPIO chip found")

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.run_http_server"):
            with pytest.raises(RuntimeError, match="No GPIO chip found"):
                main()

        # Must fire error webhook before crashing
        mock_webhooks.fire.assert_any_call(
            "error", {"source": "gpio", "error": "No GPIO chip found"}
        )

    def test_gpio_pwm_init_failure(self):
        mock_webhooks = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.side_effect = RuntimeError("PWM not available")

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.run_http_server"):
            with pytest.raises(RuntimeError, match="PWM not available"):
                main()

        mock_webhooks.fire.assert_any_call(
            "error", {"source": "gpio", "error": "PWM not available"}
        )


class TestMainOscPortInUse:
    """OSC port already bound by another process."""

    def test_osc_bind_failure_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = MagicMock()

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("[Errno 98] Address already in use")):
            with pytest.raises(OSError, match="Address already in use"):
                main()

        # Must fire start webhook (GPIO succeeded) then error webhook
        mock_webhooks.fire.assert_any_call("start")
        mock_webhooks.fire.assert_any_call(
            "error",
            {"source": "osc_bind", "error": "[Errno 98] Address already in use"},
        )


class TestMainOscServerCrash:
    """OSC server dies unexpectedly during serve_forever."""

    def test_osc_runtime_crash_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = MagicMock()

        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = RuntimeError("socket exploded")

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer", return_value=mock_server):
            with pytest.raises((RuntimeError, SystemExit)):
                main()

        mock_webhooks.fire.assert_any_call(
            "error",
            {"source": "osc_server", "error": "socket exploded"},
        )


class TestCrashHook:
    """sys.excepthook replacement fires crash webhook."""

    def test_crash_hook_fires_webhook(self):
        mock_webhooks = MagicMock()
        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = MagicMock()

        original_excepthook = sys.excepthook

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("bind fail")):
            try:
                main()
            except OSError:
                pass

        # excepthook should have been replaced
        assert sys.excepthook is not original_excepthook
        hook = sys.excepthook

        # Simulate an unhandled exception hitting the hook
        try:
            raise ValueError("something broke")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                hook(exc_type, exc_value, exc_tb)

        mock_webhooks.fire.assert_any_call(
            "crash", {"error": "ValueError: something broke"}
        )

        # Restore
        sys.excepthook = original_excepthook


class TestNoInternetResilience:
    """Webhook fires during cleanup/errors when there's no network.

    The key guarantee: the caller never blocks or crashes even if every
    webhook POST fails with ConnectionError.
    """

    def test_cleanup_does_not_block_when_webhooks_fail(self):
        """cleanup() must still zero GPIO even if webhook POST fails."""
        import requests as req

        gpio_osc.shutdown_event.clear()
        gpio_osc.pwm_a = MagicMock()
        gpio_osc.pwm_b = MagicMock()

        # Real WebhookNotifier with hooks that will fail to POST
        with patch("webhooks.requests.post",
                   side_effect=req.exceptions.ConnectionError("no network")):
            from webhooks import WebhookNotifier
            notifier = WebhookNotifier(None)  # no config file → no hooks
            # Manually inject a hook so fire() actually queues something
            notifier._hooks = [
                {"url": "https://unreachable.local/hook", "events": ["stop"]}
            ]
            gpio_osc.webhooks = notifier

            with pytest.raises(SystemExit):
                cleanup()

        # GPIO must still have been zeroed despite webhook failure
        gpio_osc.pwm_a.ChangeDutyCycle.assert_called_once_with(0)
        gpio_osc.pwm_a.stop.assert_called_once()
        gpio_osc.pwm_b.ChangeDutyCycle.assert_called_once_with(0)
        gpio_osc.pwm_b.stop.assert_called_once()

    def test_handler_error_webhook_does_not_block_on_no_network(self):
        """handle_a error path must not hang if webhook POST has no network."""
        import requests as req

        with patch("webhooks.requests.post",
                   side_effect=req.exceptions.ConnectionError("no network")):
            from webhooks import WebhookNotifier
            notifier = WebhookNotifier(None)
            notifier._hooks = [
                {"url": "https://unreachable.local/hook", "events": ["error"]}
            ]
            gpio_osc.webhooks = notifier

            mock_pwm = MagicMock()
            mock_pwm.ChangeDutyCycle.side_effect = RuntimeError("pwm dead")
            gpio_osc.pwm_a = mock_pwm

            # Must return immediately, not block waiting for POST
            start = time.time()
            handle_a("/gpio/a", 0.5)
            elapsed = time.time() - start

            assert elapsed < 1.0  # fire() is non-blocking (queue-based)

    def test_full_startup_with_no_internet(self):
        """main() startup fires 'start' webhook — must not block if no network."""
        import requests as req

        mock_gpio = MagicMock()
        mock_gpio.BCM = 11
        mock_gpio.OUT = 0
        mock_gpio.HIGH = 1
        mock_gpio.LOW = 0
        mock_gpio.PWM.return_value = MagicMock()

        with patch.object(gpio_osc, "GPIO", mock_gpio), \
             patch("webhooks.requests.post",
                   side_effect=req.exceptions.ConnectionError("no internet")), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("bind fail")):
            start = time.time()
            try:
                main()
            except OSError:
                pass
            elapsed = time.time() - start

        # Entire startup path must complete quickly even with no network
        assert elapsed < 2.0
