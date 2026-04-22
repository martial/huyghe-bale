"""Tests for gpio_osc entry point.

RPi.GPIO and pythonosc are mocked via conftest.py so these tests
run on macOS / CI without hardware. GPIO-specific handler logic lives
in tests/test_vents.py; this file covers the controller-agnostic
lifecycle: /sys/ping reply format, cleanup, and main() resilience.
"""

import sys
import time

import pytest
from unittest.mock import MagicMock, patch

import gpio_osc
from gpio_osc import handle_ping, cleanup, main, _service_name


# ── _service_name (systemd unit resolution) ─────────────────────────


class TestServiceName:
    """The Update-button restart targets whatever _service_name() returns.
    It must pick a unit that actually exists on this Pi — new-convention
    `gpio-osc-<type>` on fresh installs, legacy `gpio-osc` on old ones.
    """

    def setup_method(self):
        gpio_osc.IDENTITY = {"type": "vents", "id": "vents_x"}

    def test_prefers_per_type_unit_when_present(self):
        # `systemctl cat gpio-osc-vents.service` → 0, legacy lookup never reached
        with patch("gpio_osc.subprocess.call", return_value=0) as call:
            assert _service_name() == "gpio-osc-vents"
            # First (and only) call should be for the preferred name
            assert call.call_args_list[0].args[0][-1] == "gpio-osc-vents.service"

    def test_falls_back_to_legacy_when_per_type_missing(self):
        # First call (gpio-osc-vents) fails, second (gpio-osc) succeeds
        with patch("gpio_osc.subprocess.call", side_effect=[1, 0]):
            assert _service_name() == "gpio-osc"

    def test_returns_preferred_when_nothing_exists(self):
        # Neither unit exists — return preferred so the error log is clear.
        with patch("gpio_osc.subprocess.call", return_value=1):
            assert _service_name() == "gpio-osc-vents"


# ── handle_ping ──────────────────────────────────────────────────────


class TestHandlePing:
    def setup_method(self):
        gpio_osc.webhooks = MagicMock()
        gpio_osc.IDENTITY = {"type": "vents", "id": "vents_deadbeef"}

    def test_no_args_does_nothing(self):
        handle_ping(("192.168.1.1", 12345), "/sys/ping")
        # No exception, no webhook fire
        gpio_osc.webhooks.fire.assert_not_called()

    @patch("gpio_osc.SimpleUDPClient")
    def test_sends_pong_with_identity(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        handle_ping(("192.168.1.10", 50000), "/sys/ping", 8000)
        mock_client_cls.assert_called_once_with("192.168.1.10", 8000)
        mock_client.send_message.assert_called_once_with(
            "/sys/pong",
            ["192.168.1.10", "vents", "vents_deadbeef"],
        )

    @patch("gpio_osc.SimpleUDPClient")
    def test_pong_uses_module_default_when_main_never_ran(self, mock_client_cls):
        """If main() hasn't run, IDENTITY holds the module default placeholder."""
        gpio_osc.IDENTITY = {"type": "unknown", "id": ""}
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        handle_ping(("192.168.1.10", 50000), "/sys/ping", 8000)
        mock_client.send_message.assert_called_once_with(
            "/sys/pong", ["192.168.1.10", "unknown", ""]
        )

    def test_error_fires_webhook(self):
        handle_ping(("192.168.1.1", 12345), "/sys/ping", "not_a_port")
        gpio_osc.webhooks.fire.assert_called_once()
        assert gpio_osc.webhooks.fire.call_args[0][0] == "error"


# ── cleanup ──────────────────────────────────────────────────────────


class TestCleanup:
    def setup_method(self):
        gpio_osc.shutdown_event.clear()
        gpio_osc.webhooks = MagicMock()
        gpio_osc.controller = MagicMock()

    def test_invokes_controller_cleanup(self):
        with pytest.raises(SystemExit):
            cleanup()
        gpio_osc.controller.cleanup.assert_called_once()

    def test_fires_stop_webhook(self):
        with pytest.raises(SystemExit):
            cleanup()
        gpio_osc.webhooks.fire.assert_called_once_with("stop")

    def test_idempotent_second_call_is_noop(self):
        with pytest.raises(SystemExit):
            cleanup()
        cleanup()  # no SystemExit, no double-cleanup
        gpio_osc.controller.cleanup.assert_called_once()

    def test_handles_none_controller(self):
        gpio_osc.controller = None
        with pytest.raises(SystemExit):
            cleanup()  # must not crash


# ── main() resilience ───────────────────────────────────────────────


def _mock_identity():
    return {"type": "vents", "id": "vents_testid"}


class TestMainControllerFailure:
    def test_controller_setup_failure_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_controller = MagicMock()
        mock_controller.setup.side_effect = RuntimeError("No GPIO chip found")

        with patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.identity.load_or_create", return_value=_mock_identity()), \
             patch("gpio_osc.controllers.load", return_value=mock_controller), \
             patch("gpio_osc.run_http_server"):
            with pytest.raises(RuntimeError, match="No GPIO chip found"):
                main()

        mock_webhooks.fire.assert_any_call(
            "error", {"source": "gpio", "error": "No GPIO chip found"}
        )


class TestMainOscPortInUse:
    def test_osc_bind_failure_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_controller = MagicMock()

        with patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.identity.load_or_create", return_value=_mock_identity()), \
             patch("gpio_osc.controllers.load", return_value=mock_controller), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("[Errno 98] Address already in use")):
            with pytest.raises(OSError, match="Address already in use"):
                main()

        mock_webhooks.fire.assert_any_call("start")
        mock_webhooks.fire.assert_any_call(
            "error",
            {"source": "osc_bind", "error": "[Errno 98] Address already in use"},
        )


class TestMainOscServerCrash:
    def test_osc_runtime_crash_fires_webhook_and_raises(self):
        mock_webhooks = MagicMock()
        mock_controller = MagicMock()

        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = RuntimeError("socket exploded")

        with patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.identity.load_or_create", return_value=_mock_identity()), \
             patch("gpio_osc.controllers.load", return_value=mock_controller), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer", return_value=mock_server):
            with pytest.raises((RuntimeError, SystemExit)):
                main()

        mock_webhooks.fire.assert_any_call(
            "error",
            {"source": "osc_server", "error": "socket exploded"},
        )


class TestCrashHook:
    def test_crash_hook_fires_webhook(self):
        mock_webhooks = MagicMock()
        mock_controller = MagicMock()

        original_excepthook = sys.excepthook

        with patch("gpio_osc.WebhookNotifier", return_value=mock_webhooks), \
             patch("gpio_osc.identity.load_or_create", return_value=_mock_identity()), \
             patch("gpio_osc.controllers.load", return_value=mock_controller), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("bind fail")):
            try:
                main()
            except OSError:
                pass

        assert sys.excepthook is not original_excepthook
        hook = sys.excepthook

        try:
            raise ValueError("something broke")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(sys, "__excepthook__"):
                hook(exc_type, exc_value, exc_tb)

        mock_webhooks.fire.assert_any_call(
            "crash", {"error": "ValueError: something broke"}
        )

        sys.excepthook = original_excepthook


class TestNoInternetResilience:
    """Webhook fires during cleanup/errors when there's no network."""

    def test_cleanup_does_not_block_when_webhooks_fail(self):
        import requests as req

        gpio_osc.shutdown_event.clear()
        gpio_osc.controller = MagicMock()

        with patch("webhooks.requests.post",
                   side_effect=req.exceptions.ConnectionError("no network")):
            from webhooks import WebhookNotifier
            notifier = WebhookNotifier(None)
            notifier._hooks = [
                {"url": "https://unreachable.local/hook", "events": ["stop"]}
            ]
            gpio_osc.webhooks = notifier

            with pytest.raises(SystemExit):
                cleanup()

        gpio_osc.controller.cleanup.assert_called_once()

    def test_full_startup_with_no_internet(self):
        import requests as req

        mock_controller = MagicMock()

        with patch("webhooks.requests.post",
                   side_effect=req.exceptions.ConnectionError("no internet")), \
             patch("gpio_osc.identity.load_or_create", return_value=_mock_identity()), \
             patch("gpio_osc.controllers.load", return_value=mock_controller), \
             patch("gpio_osc.run_http_server"), \
             patch("gpio_osc.BlockingOSCUDPServer",
                   side_effect=OSError("bind fail")):
            start = time.time()
            try:
                main()
            except OSError:
                pass
            elapsed = time.time() - start

        assert elapsed < 2.0
