"""Tests for controllers.trolley — stepper driver + limit-switch logic.

Uses the shared conftest.py mocks for RPi.GPIO. Motion runs on a background
thread; tests synchronise via _idle_event rather than sleeps.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

import trolley_settings
from controllers import trolley


CALIBRATED_RAIL = 1000  # small rail for fast tests


def _reset(*, calibrated=True, calibration_direction="forward"):
    """Reset module-level state. By default install a calibrated settings block
    so tests that exercise position-follow / get_status can run without
    hitting the unhomed/uncalibrated guards. Tests that need uncalibrated
    behaviour pass calibrated=False."""
    trolley.position_steps = 0
    trolley.homed = False
    trolley.limit_error = 0
    trolley.target_steps = None
    trolley.state = trolley.STATE_IDLE
    trolley.calibration_candidate_steps = None
    trolley._calibration_started_at = 0.0
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

    settings = dict(trolley_settings.DEFAULTS)
    settings["calibration_direction"] = calibration_direction
    if calibrated:
        settings["rail_length_steps"] = CALIBRATED_RAIL
        # Disable soft-limit margin in tests so positions land exactly.
        settings["soft_limit_pct"] = 1.0
    trolley._settings = settings
    trolley._settings_pending = dict(settings)


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
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio, \
             patch.object(trolley, "trolley_settings", MagicMock(load=lambda: dict(trolley._settings),
                                                                  DEFAULTS=trolley_settings.DEFAULTS,
                                                                  ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
                                                                  VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
                                                                  is_calibrated=trolley_settings.is_calibrated,
                                                                  soft_limit_steps=trolley_settings.soft_limit_steps)):
            trolley.setup(MagicMock())
            assert mock_gpio.setmode.called
            assert mock_gpio.setup.call_count == 4
            mock_gpio.add_event_detect.assert_called_once()
            assert trolley._motion_thread is not None
            assert trolley._motion_thread.is_alive()


class TestCleanup:
    def setup_method(self):
        _reset()
        self._patch_gpio = patch.object(trolley, "GPIO", _make_gpio())
        self._patch_settings = patch.object(
            trolley, "trolley_settings",
            MagicMock(load=lambda: dict(trolley._settings),
                      DEFAULTS=trolley_settings.DEFAULTS,
                      ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
                      VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
                      is_calibrated=trolley_settings.is_calibrated,
                      soft_limit_steps=trolley_settings.soft_limit_steps),
        )
        self.mock_gpio = self._patch_gpio.start()
        self._patch_settings.start()
        trolley.setup(MagicMock())

    def teardown_method(self):
        self._patch_settings.stop()
        self._patch_gpio.stop()

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

    def test_forward_high_when_calib_forward(self):
        # default calibration_direction = "forward" → away_high=True → DIR_FORWARD = HIGH
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_dir("/trolley/dir", 1)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_DIR, 1)
            assert trolley._current_dir == trolley.DIR_FORWARD

    def test_forward_low_when_calib_reverse(self):
        # calibration_direction = "reverse" → away_high=False → DIR_FORWARD pin = LOW
        _reset(calibration_direction="reverse")
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_dir("/trolley/dir", 1)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_DIR, 0)
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
    """Set up trolley with a live motion thread + calibrated settings + homed."""
    _reset()
    gpio = _make_gpio()
    fake_settings_module = MagicMock(
        load=lambda: dict(trolley._settings),
        save=lambda block: dict(block),
        update=trolley_settings.update,
        DEFAULTS=trolley_settings.DEFAULTS,
        ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
        VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
        is_calibrated=trolley_settings.is_calibrated,
        soft_limit_steps=trolley_settings.soft_limit_steps,
    )
    with patch.object(trolley, "GPIO", gpio), \
         patch.object(trolley, "trolley_settings", fake_settings_module):
        trolley.setup(MagicMock())
        trolley.homed = True  # most tests assume already homed
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
        trolley.handle_step("/trolley/step", 100000)
        time.sleep(0.02)
        trolley.handle_stop("/trolley/stop")
        assert _wait_idle(timeout=3.0)
        assert trolley.position_steps < 100000


class TestFollow:
    def test_moves_to_target(self, running_trolley):
        trolley.handle_position("/trolley/position", 0.05)
        assert _wait_idle(timeout=5.0)
        # soft_limit_pct=1.0 in tests, so target = 0.05 * CALIBRATED_RAIL
        assert trolley.position_steps == int(round(0.05 * CALIBRATED_RAIL))

    def test_follow_stops_on_new_position(self, running_trolley):
        trolley.handle_position("/trolley/position", 1.0)
        time.sleep(0.02)
        trolley.handle_position("/trolley/position", 0.0)
        assert _wait_idle(timeout=5.0)
        assert trolley.position_steps == 0


class TestPositionGuards:
    def test_refuses_when_unhomed(self, running_trolley):
        # permissive_mode default is True since the rig setup change; flip it
        # off to exercise the strict refusal path.
        trolley._settings["permissive_mode"] = False
        trolley.homed = False
        trolley.handle_position("/trolley/position", 0.5)
        assert _wait_idle(timeout=1.0)
        assert trolley.position_steps == 0

    def test_refuses_when_uncalibrated(self):
        _reset(calibrated=False)
        gpio = _make_gpio()
        with patch.object(trolley, "GPIO", gpio):
            trolley.setup(MagicMock())
            try:
                trolley._settings["permissive_mode"] = False
                trolley.homed = True
                trolley.handle_position("/trolley/position", 0.5)
                assert _wait_idle(timeout=1.0)
                assert trolley.position_steps == 0
            finally:
                trolley.cleanup()

    def test_permissive_position_runs_without_homed_or_calibrated(self, running_trolley):
        """With permissive_mode=True (the default), /trolley/position must
        enqueue a follow even on an unhomed/uncalibrated rig. Required for
        bench testing without limit switches wired."""
        trolley._settings["permissive_mode"] = True
        trolley._settings["rail_length_steps"] = None  # uncalibrated
        trolley.homed = False
        # Drain anything pending, then send.
        while not trolley._command_queue.empty():
            try:
                trolley._command_queue.get_nowait()
            except Exception:
                break
        trolley.handle_position("/trolley/position", 0.0)
        # A follow command should have landed in the queue.
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd[0] == "follow"
        # Drain whatever motion might have started and let the loop go idle.
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_soft_limit_clamps_full_target(self, running_trolley):
        # Set a 5% soft margin and confirm /position 1.0 doesn't reach the rail end.
        trolley._settings["soft_limit_pct"] = 0.95
        trolley.handle_position("/trolley/position", 1.0)
        assert _wait_idle(timeout=5.0)
        assert trolley.position_steps == int(round(0.95 * CALIBRATED_RAIL))


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


# ── calibration state machine ──────────────────────────────────────────────


@pytest.fixture
def running_trolley_uncalibrated():
    """Live thread, but with no rail_length_steps in settings — simulates a fresh Pi."""
    _reset(calibrated=False)
    gpio = _make_gpio()
    persisted = {}

    def fake_save(block):
        nonlocal persisted
        persisted = dict(block)
        trolley._settings = dict(block)
        return dict(block)

    fake_settings_module = MagicMock(
        load=lambda: dict(persisted) if persisted else dict(trolley._settings),
        save=fake_save,
        update=trolley_settings.update,
        DEFAULTS=trolley_settings.DEFAULTS,
        ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
        VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
        is_calibrated=trolley_settings.is_calibrated,
        soft_limit_steps=trolley_settings.soft_limit_steps,
    )
    with patch.object(trolley, "GPIO", gpio), \
         patch.object(trolley, "trolley_settings", fake_settings_module):
        trolley.setup(MagicMock())
        trolley._current_speed_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        yield gpio, persisted
        trolley.cleanup()


class TestCalibrate:
    def test_start_refuses_unhomed(self, running_trolley_uncalibrated):
        trolley.homed = False
        trolley.handle_calibrate_start("/trolley/calibrate/start")
        assert trolley.state == trolley.STATE_IDLE

    def test_start_then_stop_records_candidate(self, running_trolley_uncalibrated):
        trolley.homed = True
        trolley.handle_calibrate_start("/trolley/calibrate/start")
        time.sleep(0.05)
        # While running, state should be calibrating
        assert trolley.state == trolley.STATE_CALIBRATING
        trolley.handle_calibrate_stop("/trolley/calibrate/stop")
        assert _wait_idle(timeout=3.0)
        assert trolley.calibration_candidate_steps is not None
        assert trolley.calibration_candidate_steps > 0

    def test_save_persists_candidate(self, running_trolley_uncalibrated):
        trolley.homed = True
        trolley.calibration_candidate_steps = 12345
        trolley.handle_calibrate_save("/trolley/calibrate/save")
        assert trolley._settings["rail_length_steps"] == 12345
        assert trolley.state == trolley.STATE_IDLE
        assert trolley.calibration_candidate_steps is None

    def test_cancel_discards_candidate(self, running_trolley_uncalibrated):
        trolley.calibration_candidate_steps = 999
        trolley.state = trolley.STATE_CALIBRATING
        trolley.handle_calibrate_cancel("/trolley/calibrate/cancel")
        assert trolley.calibration_candidate_steps is None
        assert trolley.state == trolley.STATE_IDLE

    def test_save_refuses_zero_candidate(self, running_trolley_uncalibrated):
        trolley.handle_calibrate_save("/trolley/calibrate/save")
        # rail_length_steps stays None
        assert trolley._settings.get("rail_length_steps") is None

    def test_start_with_direction_arg_persists_setting(self, running_trolley_uncalibrated):
        trolley.homed = True
        trolley.handle_calibrate_start("/trolley/calibrate/start", "reverse")
        assert trolley._settings["calibration_direction"] == "reverse"
        trolley.handle_stop("/trolley/stop")
        assert _wait_idle(timeout=3.0)


# ── settings ────────────────────────────────────────────────────────────────


class TestConfigSet:
    def setup_method(self):
        _reset()

    def test_stage_then_save_persists(self):
        saved = {}
        with patch.object(trolley, "trolley_settings", MagicMock(
            ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
            update=trolley_settings.update,
            save=lambda block: saved.update(block) or dict(block),
            load=lambda: dict(trolley._settings),
            DEFAULTS=trolley_settings.DEFAULTS,
            VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
            is_calibrated=trolley_settings.is_calibrated,
            soft_limit_steps=trolley_settings.soft_limit_steps,
        )):
            trolley.handle_config_set("/trolley/config/set", "max_speed_hz", 1500)
            assert trolley._settings_pending["max_speed_hz"] == 1500.0
            # Setting alone does not persist
            assert "max_speed_hz" not in saved
            trolley.handle_config_save("/trolley/config/save")
            assert saved["max_speed_hz"] == 1500.0

    def test_invalid_key_ignored(self):
        with patch.object(trolley, "trolley_settings", MagicMock(
            ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
            update=trolley_settings.update,
            DEFAULTS=trolley_settings.DEFAULTS,
            VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
            is_calibrated=trolley_settings.is_calibrated,
            soft_limit_steps=trolley_settings.soft_limit_steps,
        )):
            trolley.handle_config_set("/trolley/config/set", "bogus_key", 1)
            assert "bogus_key" not in trolley._settings_pending

    def test_invalid_value_ignored(self):
        with patch.object(trolley, "trolley_settings", MagicMock(
            ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
            update=trolley_settings.update,
            DEFAULTS=trolley_settings.DEFAULTS,
            VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
            is_calibrated=trolley_settings.is_calibrated,
            soft_limit_steps=trolley_settings.soft_limit_steps,
        )):
            before = dict(trolley._settings_pending)
            trolley.handle_config_set("/trolley/config/set", "calibration_direction", "diagonal")
            assert trolley._settings_pending == before


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
        assert r["calibrated"] is True
        assert r["state"] == trolley.STATE_IDLE

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
        assert d["calibrated"] is True
        assert d["calibration_direction"] == "forward"

    def test_get_status_normalises_position(self):
        _reset()
        trolley.position_steps = CALIBRATED_RAIL // 2
        s = trolley.get_status()
        assert s["position"] == pytest.approx(0.5, abs=0.01)
        assert s["position_steps"] == trolley.position_steps
        assert s["calibrated"] == 1
        assert s["state"] == trolley.STATE_IDLE

    def test_status_osc_args_shape(self):
        _reset()
        trolley.position_steps = CALIBRATED_RAIL // 4
        trolley.homed = True
        args = trolley.get_status_osc_args()
        # [position, limit, homed, state, calibrated]
        assert len(args) == 5
        assert isinstance(args[0], float)
        assert isinstance(args[3], str)
        assert args[3] == trolley.STATE_IDLE
        assert args[4] == 1

    def test_status_uncalibrated_falls_back_to_legacy(self):
        _reset(calibrated=False)
        s = trolley.get_status()
        assert s["calibrated"] == 0
        assert s["max_steps"] == trolley.TROLLEY_MAX_STEPS  # legacy fallback
