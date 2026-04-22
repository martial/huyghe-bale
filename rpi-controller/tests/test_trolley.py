"""Tests for controllers.trolley — stepper driver + limit-switch logic.

Uses the shared conftest.py mocks for RPi.GPIO. Motion runs on a background
thread; tests synchronise via _idle_event rather than sleeps.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from controllers import trolley


def _reset():
    """Reset module-level state so each test starts clean."""
    trolley.position_steps = 0
    trolley.homed = False
    trolley.limit_error = 0
    trolley.target_steps = None
    trolley._current_dir = trolley.DIR_FORWARD
    trolley._current_speed_hz = 1000.0
    trolley._enabled = False
    trolley._webhooks = MagicMock()
    trolley._abort_event.clear()
    trolley._shutdown_event.clear()
    trolley._idle_event.set()
    while not trolley._command_queue.empty():
        try:
            trolley._command_queue.get_nowait()
        except Exception:
            break


def _wait_idle(timeout=3.0):
    return trolley._idle_event.wait(timeout=timeout)


def _make_gpio():
    gpio = MagicMock()
    gpio.BCM = 11
    gpio.OUT = 0
    gpio.IN = 1
    gpio.HIGH = 1
    gpio.LOW = 0
    gpio.PUD_DOWN = 21
    gpio.BOTH = 3
    return gpio


# ── setup / cleanup ─────────────────────────────────────────────────────────


class TestSetup:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        trolley.cleanup()

    def test_configures_pins_and_starts_thread(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.setup(MagicMock())
            assert mock_gpio.setmode.called
            # 3 outputs (DIR/PUL/ENA) + 1 input (LIM)
            assert mock_gpio.setup.call_count == 4
            mock_gpio.add_event_detect.assert_called_once()
            assert trolley._motion_thread is not None
            assert trolley._motion_thread.is_alive()


class TestCleanup:
    def setup_method(self):
        _reset()
        self._patch = patch.object(trolley, "GPIO", _make_gpio())
        self.mock_gpio = self._patch.start()
        trolley.setup(MagicMock())

    def teardown_method(self):
        self._patch.stop()

    def test_stops_thread_and_disables_ena(self):
        trolley.cleanup()
        assert any(
            c.args == (trolley.PIN_STEP_ENA, 1)
            for c in self.mock_gpio.output.call_args_list
        )
        self.mock_gpio.remove_event_detect.assert_called_once_with(trolley.PIN_LIM_SWITCH)
        assert not trolley._motion_thread.is_alive()


# ── raw handlers (no thread needed) ─────────────────────────────────────────


class TestHandleEnable:
    def setup_method(self):
        _reset()

    def test_enable_pulls_ena_low(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_enable("/trolley/enable", 1)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_ENA, 0)
            assert trolley._enabled is True

    def test_disable_pulls_ena_high(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_enable("/trolley/enable", 0)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_ENA, 1)
            assert trolley._enabled is False

    def test_updates_last_osc_time(self):
        before = time.time()
        with patch.object(trolley, "GPIO", _make_gpio()):
            trolley.handle_enable("/trolley/enable", 1)
        assert trolley.last_osc_time >= before


class TestHandleDir:
    def setup_method(self):
        _reset()

    def test_forward(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_dir("/trolley/dir", 1)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_DIR, 1)
            assert trolley._current_dir == trolley.DIR_FORWARD

    def test_reverse(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_dir("/trolley/dir", 0)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_DIR, 0)
            assert trolley._current_dir == trolley.DIR_REVERSE


class TestHandleSpeed:
    def setup_method(self):
        _reset()

    def test_scales_mid(self):
        trolley.handle_speed("/trolley/speed", 0.5)
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        assert trolley._current_speed_hz == pytest.approx(max_hz * 0.5)

    def test_zero(self):
        trolley.handle_speed("/trolley/speed", 0.0)
        assert trolley._current_speed_hz == 0.0

    def test_clamps_high(self):
        trolley.handle_speed("/trolley/speed", 2.0)
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        assert trolley._current_speed_hz == pytest.approx(max_hz)


# ── motion (thread + queue) ─────────────────────────────────────────────────


@pytest.fixture
def running_trolley():
    """Set up trolley with a live motion thread, yield, tear down."""
    _reset()
    gpio = _make_gpio()
    with patch.object(trolley, "GPIO", gpio):
        trolley.setup(MagicMock())
        trolley._current_speed_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        yield gpio
        trolley.cleanup()


class TestStepBurst:
    def test_forward_increments_position(self, running_trolley):
        trolley.handle_dir("/trolley/dir", 1)
        trolley.handle_step("/trolley/step", 10)
        assert _wait_idle()
        assert trolley.position_steps == 10

    def test_reverse_decrements_position(self, running_trolley):
        trolley.position_steps = 20
        trolley.handle_dir("/trolley/dir", 0)
        trolley.handle_step("/trolley/step", 5)
        assert _wait_idle()
        assert trolley.position_steps == 15

    def test_reverse_never_goes_below_zero(self, running_trolley):
        trolley.position_steps = 3
        trolley.handle_dir("/trolley/dir", 0)
        trolley.handle_step("/trolley/step", 10)
        assert _wait_idle()
        assert trolley.position_steps == 0


class TestStop:
    def test_stop_aborts_burst(self, running_trolley):
        trolley.handle_dir("/trolley/dir", 1)
        trolley.handle_step("/trolley/step", 100000)  # long burst
        time.sleep(0.02)
        trolley.handle_stop("/trolley/stop")
        assert _wait_idle(timeout=3.0)
        assert trolley.position_steps < 100000


class TestFollow:
    def test_moves_to_target(self, running_trolley):
        trolley.handle_position("/trolley/position", 0.02)
        assert _wait_idle(timeout=5.0)
        expected = int(round(0.02 * trolley.TROLLEY_MAX_STEPS))
        assert trolley.position_steps == expected

    def test_follow_stops_on_new_position(self, running_trolley):
        trolley.handle_position("/trolley/position", 1.0)  # huge target
        time.sleep(0.02)
        trolley.handle_position("/trolley/position", 0.0)  # cancel → go home
        assert _wait_idle(timeout=5.0)
        assert trolley.position_steps == 0


class TestLimitSwitch:
    def test_isr_resets_position_on_home(self, running_trolley):
        trolley.position_steps = 500
        trolley._current_dir = trolley.DIR_REVERSE
        running_trolley.input.return_value = running_trolley.HIGH
        trolley._limit_switch_isr(trolley.PIN_LIM_SWITCH)
        assert trolley.position_steps == 0
        assert trolley.homed is True
        assert trolley.limit_error == 1

    def test_isr_clears_limit_on_release(self, running_trolley):
        trolley.limit_error = 1
        running_trolley.input.return_value = running_trolley.LOW
        trolley._limit_switch_isr(trolley.PIN_LIM_SWITCH)
        assert trolley.limit_error == 0

    def test_reverse_aborts_at_limit(self, running_trolley):
        trolley.limit_error = 1
        trolley._current_dir = trolley.DIR_REVERSE
        trolley.handle_step("/trolley/step", 100)
        assert _wait_idle()
        assert trolley.position_steps == 0


# ── HTTP test surface ───────────────────────────────────────────────────────


class TestHttpTest:
    def setup_method(self):
        _reset()

    def test_unknown_command(self):
        with patch.object(trolley, "GPIO", _make_gpio()):
            r = trolley.handle_http_test({"command": "teleport", "value": 1})
        assert r["ok"] is False

    def test_enable_via_http(self):
        with patch.object(trolley, "GPIO", _make_gpio()):
            r = trolley.handle_http_test({"command": "enable", "value": 1})
        assert r["ok"] is True
        assert r["enabled"] is True

    def test_reports_position_and_limit(self):
        trolley.position_steps = 123
        trolley.limit_error = 1
        trolley.homed = True
        with patch.object(trolley, "GPIO", _make_gpio()):
            r = trolley.handle_http_test({"command": "stop"})
        assert r["position_steps"] == 123
        assert r["limit"] == 1
        assert r["homed"] is True


# ── describe / get_status ───────────────────────────────────────────────────


class TestDescribeAndStatus:
    def test_describe(self):
        _reset()
        d = trolley.describe()
        assert d["controller"] == "trolley"
        assert "pins" in d

    def test_get_status_normalises_position(self):
        _reset()
        trolley.position_steps = int(trolley.TROLLEY_MAX_STEPS / 2)
        s = trolley.get_status()
        assert s["position"] == pytest.approx(0.5, abs=0.01)
        assert s["position_steps"] == trolley.position_steps
