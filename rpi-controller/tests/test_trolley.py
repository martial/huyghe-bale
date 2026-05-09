"""Tests for controllers.trolley — stepper driver + dual limit switches.

Uses the shared conftest.py mocks for RPi.GPIO. Motion runs on a background
thread; tests synchronise via _idle_event rather than sleeps.
"""

import math
import time
from unittest.mock import MagicMock, patch

import pytest

import trolley_settings
from controllers import trolley


# Pick wheel radius so 2π × R == steps_per_rev: with microsteps=1, that gives
# steps_per_mm = 1, so the derived rail-step count equals rail_length_mm.
TEST_STEPS_PER_REV = 200
TEST_MICROSTEPS = 1
TEST_WHEEL_RADIUS_MM = TEST_STEPS_PER_REV / (2.0 * math.pi)
TEST_RAIL_LENGTH_MM = 1000.0
CALIBRATED_RAIL = round(TEST_RAIL_LENGTH_MM * TEST_STEPS_PER_REV * TEST_MICROSTEPS
                        / (2.0 * math.pi * TEST_WHEEL_RADIUS_MM))  # = 1000


def _build_settings(*, calibrated=True, calibration_direction="forward"):
    settings = dict(trolley_settings.DEFAULTS)
    settings["calibration_direction"] = calibration_direction
    settings["steps_per_rev"] = TEST_STEPS_PER_REV
    settings["microsteps"] = TEST_MICROSTEPS
    if calibrated:
        settings["rail_length_mm"] = TEST_RAIL_LENGTH_MM
        settings["wheel_radius_mm"] = TEST_WHEEL_RADIUS_MM
        settings["soft_limit_pct"] = 1.0  # exact landings in tests
    return settings


def _reset(*, calibrated=True, calibration_direction="forward"):
    """Reset module-level state. By default install a configured settings
    block so tests that exercise position-follow / get_status can run without
    hitting the unhomed/unconfigured guards."""
    trolley.position_steps = 0
    trolley.homed = False
    trolley.limit_error = 0
    trolley.far_limit_error = 0
    trolley.alarm_locked = False
    trolley.alarm_active = 0
    trolley.target_steps = None
    trolley.state = trolley.STATE_IDLE
    trolley._current_dir = trolley.DIR_FORWARD
    trolley._current_speed_hz = 1000.0
    trolley._enabled = False
    trolley._accel_time_s = 0.0
    trolley._decel_time_s = 0.0
    trolley._webhooks = MagicMock()
    trolley._abort_event.clear()
    trolley._shutdown_event.clear()
    trolley._idle_event.set()
    while not trolley._command_queue.empty():
        try:
            trolley._command_queue.get_nowait()
        except Exception:
            break

    settings = _build_settings(calibrated=calibrated, calibration_direction=calibration_direction)
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


def _settings_mock_with_real_helpers():
    """A MagicMock for trolley_settings whose helpers point at the real module
    so derivation/validation use real math."""
    return MagicMock(
        load=lambda: dict(trolley._settings),
        save=lambda block: dict(block),
        update=trolley_settings.update,
        DEFAULTS=trolley_settings.DEFAULTS,
        ALLOWED_KEYS=trolley_settings.ALLOWED_KEYS,
        VALID_DIRECTIONS=trolley_settings.VALID_DIRECTIONS,
        is_calibrated=trolley_settings.is_calibrated,
        derived_rail_length_steps=trolley_settings.derived_rail_length_steps,
        soft_limit_steps=trolley_settings.soft_limit_steps,
    )


# ── derivation math ─────────────────────────────────────────────────────────


class TestDerivation:
    def test_derived_steps_round_trip(self):
        s = _build_settings()
        # rail = 1000 mm, wheel chosen so steps_per_mm = 1 → 1000 steps
        assert trolley_settings.derived_rail_length_steps(s) == 1000

    def test_derived_zero_when_rail_missing(self):
        s = _build_settings(calibrated=False)
        assert trolley_settings.derived_rail_length_steps(s) == 0

    def test_derived_zero_when_wheel_missing(self):
        s = _build_settings()
        s["wheel_radius_mm"] = None
        assert trolley_settings.derived_rail_length_steps(s) == 0

    def test_is_calibrated_true_only_when_both_set(self):
        s = _build_settings()
        assert trolley_settings.is_calibrated(s) is True
        s["wheel_radius_mm"] = None
        assert trolley_settings.is_calibrated(s) is False

    def test_lead_8mm_per_rev_equivalent(self):
        # 2π × R = 8 mm/rev (legacy lead). With 200 steps/rev × 16 microsteps
        # → 400 steps/mm. A 5 m rail → 2,000,000 steps.
        s = dict(trolley_settings.DEFAULTS)
        s["rail_length_mm"] = 5000.0
        s["wheel_radius_mm"] = 8.0 / (2.0 * math.pi)
        s["steps_per_rev"] = 200
        s["microsteps"] = 16
        assert abs(trolley_settings.derived_rail_length_steps(s) - 2_000_000) <= 1


# ── setup / cleanup ─────────────────────────────────────────────────────────


class TestSetup:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        trolley.cleanup()

    def test_configures_pins_and_starts_thread(self):
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio, \
             patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.setup(MagicMock())
            assert mock_gpio.setmode.called
            # DIR + PUL + ENA + LIM_HOME + LIM_FAR + ALARM_1 + ALARM_2
            assert mock_gpio.setup.call_count == 7
            # Four ISRs: home + far + alarm_1 + alarm_2
            assert mock_gpio.add_event_detect.call_count == 4
            assert trolley._motion_thread is not None
            assert trolley._motion_thread.is_alive()


class TestCleanup:
    def setup_method(self):
        _reset()
        self._patch_gpio = patch.object(trolley, "GPIO", _make_gpio())
        self._patch_settings = patch.object(
            trolley, "trolley_settings", _settings_mock_with_real_helpers(),
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
        # Both ISRs should be torn down
        removed = {c.args[0] for c in self.mock_gpio.remove_event_detect.call_args_list}
        assert trolley.PIN_LIM_SWITCH in removed
        assert trolley.PIN_LIM_SWITCH_FAR in removed
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
        with patch.object(trolley, "GPIO", _make_gpio()) as mock_gpio:
            trolley.handle_dir("/trolley/dir", 1)
            mock_gpio.output.assert_called_with(trolley.PIN_STEP_DIR, 1)
            assert trolley._current_dir == trolley.DIR_FORWARD

    def test_forward_low_when_calib_reverse(self):
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

    def test_scales_below_cap(self):
        trolley.handle_speed("/trolley/speed", 0.2)
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        assert trolley._current_speed_hz == pytest.approx(max_hz * 0.2)

    def test_zero(self):
        trolley.handle_speed("/trolley/speed", 0.0)
        assert trolley._current_speed_hz == 0.0

    def test_clamps_to_safety_cap(self):
        # Hard safety cap: any /trolley/speed above MAX_SPEED_PCT is clamped.
        trolley.handle_speed("/trolley/speed", 2.0)
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        assert trolley._current_speed_hz == pytest.approx(max_hz * trolley.MAX_SPEED_PCT)

    def test_speed_to_delay_floor_enforces_cap(self):
        # Even if a caller passes a Hz value above the firmware's full bandwidth
        # × MAX_SPEED_PCT, _speed_to_delay clamps the half-period.
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        capped_hz = max_hz * trolley.MAX_SPEED_PCT
        capped_min_delay = 1.0 / (2.0 * capped_hz)
        # Asking for max_hz returns the capped delay (slower) not the raw min.
        assert trolley._speed_to_delay(max_hz) == pytest.approx(capped_min_delay)
        # Asking below the cap is unchanged.
        assert trolley._speed_to_delay(capped_hz / 2) == pytest.approx(1.0 / (2.0 * (capped_hz / 2)))


class TestHandleAccelDecel:
    def setup_method(self):
        _reset()

    def test_accel_sets_state(self):
        trolley.handle_accel("/trolley/accel", 1.5)
        assert trolley._accel_time_s == pytest.approx(1.5)

    def test_decel_sets_state(self):
        trolley.handle_decel("/trolley/decel", 0.8)
        assert trolley._decel_time_s == pytest.approx(0.8)

    def test_accel_clamps_negative(self):
        trolley.handle_accel("/trolley/accel", -1.0)
        assert trolley._accel_time_s == 0.0

    def test_accel_clamps_high(self):
        trolley.handle_accel("/trolley/accel", 100.0)
        assert trolley._accel_time_s == 10.0

    def test_decel_clamps_high(self):
        trolley.handle_decel("/trolley/decel", 50.0)
        assert trolley._decel_time_s == 10.0

    def test_no_args_is_noop(self):
        trolley._accel_time_s = 2.0
        trolley.handle_accel("/trolley/accel")
        assert trolley._accel_time_s == 2.0

    def test_handle_accel_stages_for_persistence(self):
        """Live OSC writes must round-trip via /trolley/config/save without
        the operator having to re-send the same value via /trolley/config/set."""
        trolley.handle_accel("/trolley/accel", 1.5)
        trolley.handle_decel("/trolley/decel", 0.7)
        assert trolley._settings_pending["accel_time_s"] == pytest.approx(1.5)
        assert trolley._settings_pending["decel_time_s"] == pytest.approx(0.7)


class TestPulseTrainRamp:
    """Direct unit tests on _run_pulse_train — patches _pulse_once to capture
    the delay sequence without sleeping."""

    def setup_method(self):
        _reset()

    def _capture_delays(self, total_steps, target_hz, accel_s, decel_s):
        delays = []

        def fake_pulse_once(delay_s):
            delays.append(delay_s)
            return True

        with patch.object(trolley, "_pulse_once", side_effect=fake_pulse_once), \
             patch.object(trolley, "_apply_step_delta"):
            trolley._run_pulse_train(total_steps, target_hz, accel_s, decel_s)
        return delays

    def test_zero_ramps_uses_constant_delay(self):
        delays = self._capture_delays(50, 500.0, 0.0, 0.0)
        assert len(delays) == 50
        assert all(d == delays[0] for d in delays)

    def test_trapezoidal_long_move_has_three_phases(self):
        # target=500 Hz, accel=1.0 s → steps_a ≈ 250; decel=1.0 s → steps_d ≈ 250.
        # total=1000 → cruise = 500 steps. Plenty of room for full trapezoid.
        delays = self._capture_delays(1000, 500.0, 1.0, 1.0)
        assert len(delays) == 1000
        # Accel phase: delays should monotonically *decrease* (slower → faster).
        # First few delays >> last few accel delays.
        assert delays[0] > delays[200]
        # Cruise: middle delays all equal to _speed_to_delay(500).
        cruise_expected = trolley._speed_to_delay(500.0)
        # The middle 100 samples should all be the cruise delay.
        for d in delays[400:500]:
            assert d == pytest.approx(cruise_expected)
        # Decel phase: delays monotonically *increase* (faster → slower).
        assert delays[-1] > delays[-200]

    def test_triangular_short_move_emits_exact_step_count(self):
        # Ramp budget would be 2*500*0.5/2 = 500 steps but we only have 100.
        delays = self._capture_delays(100, 500.0, 0.5, 0.5)
        assert len(delays) == 100  # never runs over

    def test_constant_path_matches_legacy(self):
        # When ramps are zero the delay should be _speed_to_delay(target_hz)
        # for every pulse — same as the legacy loop.
        target = 800.0
        delays = self._capture_delays(20, target, 0.0, 0.0)
        expected = trolley._speed_to_delay(target)
        assert all(d == expected for d in delays)


class TestRampedStepBurst:
    """Integration: /trolley/step honours _accel_time_s / _decel_time_s
    and still emits the requested number of steps."""

    def test_ramped_burst_emits_exact_count(self, running_trolley):
        trolley._accel_time_s = 0.05
        trolley._decel_time_s = 0.05
        trolley._current_speed_hz = 200.0  # keep the test fast
        trolley.handle_dir("/trolley/dir", 1)
        trolley.handle_step("/trolley/step", 30)
        assert _wait_idle(timeout=5.0)
        assert trolley.position_steps == 30

    def test_zero_ramps_unchanged_behaviour(self, running_trolley):
        # Default ramps = 0 — must behave exactly like before (covered by
        # the existing TestStepBurst suite, but assert here too for clarity).
        trolley._accel_time_s = 0.0
        trolley._decel_time_s = 0.0
        trolley.handle_dir("/trolley/dir", 1)
        trolley.handle_step("/trolley/step", 12)
        assert _wait_idle()
        assert trolley.position_steps == 12


# ── motion (thread + queue) ─────────────────────────────────────────────────


@pytest.fixture
def running_trolley():
    """Set up trolley with a live motion thread + configured settings + homed."""
    _reset()
    gpio = _make_gpio()
    with patch.object(trolley, "GPIO", gpio), \
         patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
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
        trolley._settings["permissive_mode"] = False
        trolley.homed = False
        trolley.handle_position("/trolley/position", 0.5)
        assert _wait_idle(timeout=1.0)
        assert trolley.position_steps == 0

    def test_refuses_when_unconfigured(self):
        _reset(calibrated=False)
        gpio = _make_gpio()
        with patch.object(trolley, "GPIO", gpio), \
             patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.setup(MagicMock())
            try:
                trolley._settings["permissive_mode"] = False
                trolley.homed = True
                trolley.handle_position("/trolley/position", 0.5)
                assert _wait_idle(timeout=1.0)
                assert trolley.position_steps == 0
            finally:
                trolley.cleanup()

    def test_permissive_position_runs_without_homed_or_configured(self, running_trolley):
        """With permissive_mode=True (the default), /trolley/position must
        enqueue a follow even on an unhomed/unconfigured rig. Required for
        bench testing without limit switches wired."""
        trolley._settings["permissive_mode"] = True
        trolley._settings["rail_length_mm"] = None  # unconfigured
        trolley._settings["wheel_radius_mm"] = None
        trolley.homed = False
        while not trolley._command_queue.empty():
            try:
                trolley._command_queue.get_nowait()
            except Exception:
                break
        trolley.handle_position("/trolley/position", 0.0)
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd[0] == "follow"
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_soft_limit_clamps_full_target(self, running_trolley):
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


class TestFarLimitSwitch:
    def test_isr_pins_position_on_far(self, running_trolley):
        trolley.position_steps = 0
        trolley._current_dir = trolley.DIR_FORWARD
        running_trolley.input.return_value = running_trolley.HIGH
        trolley._far_limit_switch_isr(trolley.PIN_LIM_SWITCH_FAR)
        assert trolley.position_steps == CALIBRATED_RAIL
        assert trolley.homed is True
        assert trolley.far_limit_error == 1

    def test_isr_clears_far_on_release(self, running_trolley):
        trolley.far_limit_error = 1
        running_trolley.input.return_value = running_trolley.LOW
        trolley._far_limit_switch_isr(trolley.PIN_LIM_SWITCH_FAR)
        assert trolley.far_limit_error == 0

    def test_forward_aborts_at_far_limit(self, running_trolley):
        trolley.far_limit_error = 1
        trolley._current_dir = trolley.DIR_FORWARD
        trolley.position_steps = 100
        trolley.handle_step("/trolley/step", 200)
        assert _wait_idle()
        # Symmetric guard: forward pulses must abort when far_limit_error is high
        assert trolley.position_steps == 100


class TestAlarmLock:
    def setup_method(self):
        _reset()
        # Default polarity is "disabled" (opt-in); tests that exercise the
        # latching behaviour need to flip it on explicitly.
        trolley._settings["alarm_polarity"] = "active_high"

    def teardown_method(self):
        trolley.alarm_locked = False
        trolley.alarm_active = 0
        trolley._settings["alarm_polarity"] = trolley_settings.DEFAULTS["alarm_polarity"]

    def _gpio_with_alarm(self, a1=False, a2=False):
        gpio = _make_gpio()

        def fake_input(pin):
            if pin == trolley.PIN_ALARM_1:
                return gpio.HIGH if a1 else gpio.LOW
            if pin == trolley.PIN_ALARM_2:
                return gpio.HIGH if a2 else gpio.LOW
            return gpio.LOW

        gpio.input.side_effect = fake_input
        return gpio

    def test_isr_latches_lock_and_disables_driver(self):
        gpio = self._gpio_with_alarm(a1=True)
        with patch.object(trolley, "GPIO", gpio):
            trolley._alarm_isr(trolley.PIN_ALARM_1)
        assert trolley.alarm_locked is True
        # ENA pulled HIGH = driver disabled (active LOW).
        assert any(
            c.args == (trolley.PIN_STEP_ENA, 1)
            for c in gpio.output.call_args_list
        )

    def test_isr_with_no_alarm_does_not_latch(self):
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=False, a2=False)):
            trolley._alarm_isr(trolley.PIN_ALARM_1)
        assert trolley.alarm_locked is False

    def test_motion_handlers_refused_when_locked(self):
        trolley.alarm_locked = True
        gpio = _make_gpio()
        with patch.object(trolley, "GPIO", gpio):
            # All motion handlers must short-circuit.
            trolley.handle_enable("/trolley/enable", 1)
            assert trolley._enabled is False
            trolley.handle_step("/trolley/step", 100)
            assert trolley._command_queue.empty()
            trolley.handle_home("/trolley/home", "reverse")
            assert trolley._command_queue.empty()
            trolley.handle_position("/trolley/position", 0.5)
            assert trolley._command_queue.empty()

    def test_reset_succeeds_when_pins_low(self):
        trolley.alarm_locked = True
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=False, a2=False)):
            trolley.handle_alarm_reset("/trolley/alarm/reset")
        assert trolley.alarm_locked is False

    def test_reset_refused_when_pin_still_high(self):
        trolley.alarm_locked = True
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=True)):
            trolley.handle_alarm_reset("/trolley/alarm/reset")
        assert trolley.alarm_locked is True

    def test_status_includes_alarm_fields(self):
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=True)):
            s = trolley.get_status()
        assert s["alarm"] == 1
        # alarm_locked tracks the latched flag, not the pin.
        assert s["alarm_locked"] == 0
        trolley.alarm_locked = True
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=False)):
            s2 = trolley.get_status()
        assert s2["alarm"] == 0
        assert s2["alarm_locked"] == 1

    def test_active_low_polarity_inverts_pin_reading(self):
        trolley._settings["alarm_polarity"] = "active_low"
        # Pin HIGH = OK in active_low wiring.
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=True, a2=True)):
            a1, a2 = trolley._read_alarm_pins()
        assert (a1, a2) == (0, 0)
        # Pin LOW = fault in active_low wiring.
        with patch.object(trolley, "GPIO", self._gpio_with_alarm(a1=False, a2=False)):
            a1, a2 = trolley._read_alarm_pins()
        assert (a1, a2) == (1, 1)

    def test_disabled_polarity_never_latches(self):
        trolley._settings["alarm_polarity"] = "disabled"
        gpio = self._gpio_with_alarm(a1=True, a2=True)
        with patch.object(trolley, "GPIO", gpio):
            trolley._alarm_isr(trolley.PIN_ALARM_1)
        assert trolley.alarm_locked is False


class TestLimitSwitchSwap:
    def setup_method(self):
        _reset()

    def test_default_is_swapped_for_this_rig(self):
        # Project wiring: home switch is on PIN_LIM_SWITCH_FAR by default.
        assert trolley._settings["limit_switches_swapped"] is True
        assert trolley._home_pin() == trolley.PIN_LIM_SWITCH_FAR
        assert trolley._far_pin() == trolley.PIN_LIM_SWITCH

    def test_unswapped_uses_direct_mapping(self):
        trolley._settings["limit_switches_swapped"] = False
        assert trolley._home_pin() == trolley.PIN_LIM_SWITCH
        assert trolley._far_pin() == trolley.PIN_LIM_SWITCH_FAR


# ── home command ────────────────────────────────────────────────────────────


class TestHome:
    def test_home_default_drives_reverse(self, running_trolley):
        trolley.position_steps = 50
        trolley.homed = False
        trolley.handle_home("/trolley/home")
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd == ("home", trolley.DIR_REVERSE)
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_home_reverse_string(self, running_trolley):
        trolley.handle_home("/trolley/home", "reverse")
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd == ("home", trolley.DIR_REVERSE)
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_home_forward_string(self, running_trolley):
        trolley.handle_home("/trolley/home", "forward")
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd == ("home", trolley.DIR_FORWARD)
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_home_int_one_means_forward(self, running_trolley):
        trolley.handle_home("/trolley/home", 1)
        cmd = trolley._command_queue.get(timeout=1.0)
        assert cmd == ("home", trolley.DIR_FORWARD)
        trolley._abort_event.set()
        _wait_idle(timeout=2.0)

    def test_home_reverse_stops_on_home_limit(self, running_trolley):
        trolley.position_steps = 200
        trolley.homed = False

        def trip_after_some_pulses():
            time.sleep(0.05)
            trolley.limit_error = 1
            trolley.position_steps = 0
            trolley.homed = True

        import threading
        t = threading.Thread(target=trip_after_some_pulses, daemon=True)
        t.start()
        trolley.handle_home("/trolley/home", "reverse")
        assert _wait_idle(timeout=5.0)
        assert trolley.homed is True
        assert trolley.position_steps == 0
        assert trolley.state == trolley.STATE_IDLE

    def test_home_forward_stops_on_far_limit(self, running_trolley):
        trolley.position_steps = 0
        trolley.homed = False

        def trip_after_some_pulses():
            time.sleep(0.05)
            trolley.far_limit_error = 1
            trolley.position_steps = CALIBRATED_RAIL
            trolley.homed = True

        import threading
        t = threading.Thread(target=trip_after_some_pulses, daemon=True)
        t.start()
        trolley.handle_home("/trolley/home", "forward")
        assert _wait_idle(timeout=5.0)
        assert trolley.homed is True
        assert trolley.position_steps == CALIBRATED_RAIL
        assert trolley.state == trolley.STATE_IDLE


# ── settings ────────────────────────────────────────────────────────────────


class TestConfigSet:
    def setup_method(self):
        _reset()

    def test_stage_then_save_persists(self):
        saved = {}
        mock = _settings_mock_with_real_helpers()
        mock.save = lambda block: saved.update(block) or dict(block)
        with patch.object(trolley, "trolley_settings", mock):
            trolley.handle_config_set("/trolley/config/set", "max_speed_hz", 1500)
            assert trolley._settings_pending["max_speed_hz"] == 1500.0
            assert "max_speed_hz" not in saved
            trolley.handle_config_save("/trolley/config/save")
            assert saved["max_speed_hz"] == 1500.0

    def test_set_rail_length_mm(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.handle_config_set("/trolley/config/set", "rail_length_mm", 2500.0)
            assert trolley._settings_pending["rail_length_mm"] == 2500.0

    def test_set_wheel_radius_mm(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.handle_config_set("/trolley/config/set", "wheel_radius_mm", 1.27)
            assert trolley._settings_pending["wheel_radius_mm"] == 1.27

    def test_invalid_key_ignored(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.handle_config_set("/trolley/config/set", "bogus_key", 1)
            assert "bogus_key" not in trolley._settings_pending

    def test_invalid_value_ignored(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            before = dict(trolley._settings_pending)
            trolley.handle_config_set("/trolley/config/set", "calibration_direction", "diagonal")
            assert trolley._settings_pending == before

    def test_set_accel_and_decel(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            trolley.handle_config_set("/trolley/config/set", "accel_time_s", 1.5)
            trolley.handle_config_set("/trolley/config/set", "decel_time_s", 0.7)
            assert trolley._settings_pending["accel_time_s"] == 1.5
            assert trolley._settings_pending["decel_time_s"] == 0.7

    def test_accel_out_of_range_rejected(self):
        with patch.object(trolley, "trolley_settings", _settings_mock_with_real_helpers()):
            before = trolley._settings_pending.get("accel_time_s")
            trolley.handle_config_set("/trolley/config/set", "accel_time_s", 99.0)
            assert trolley._settings_pending.get("accel_time_s") == before


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

    def test_calibrate_command_no_longer_recognised(self):
        with patch.object(trolley, "GPIO", _make_gpio()):
            r = trolley.handle_http_test({"command": "calibrate_start", "value": "forward"})
        assert r["ok"] is False


# ── describe / get_status ───────────────────────────────────────────────────


class TestDescribeAndStatus:
    def test_describe(self):
        _reset()
        d = trolley.describe()
        assert d["controller"] == "trolley"
        assert "pins" in d
        # Default config is swapped: home switch on PIN_LIM_SWITCH_FAR, far on PIN_LIM_SWITCH.
        assert d["pins"]["limit"] == trolley.PIN_LIM_SWITCH_FAR
        assert d["pins"]["limit_far"] == trolley.PIN_LIM_SWITCH
        assert d["limit_switches_swapped"] is True
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
        trolley._enabled = True
        trolley._current_dir = trolley.DIR_FORWARD
        trolley._accel_time_s = 0.5
        trolley._decel_time_s = 0.25
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        trolley._current_speed_hz = 0.3 * max_hz
        with patch.object(trolley, "GPIO", _make_gpio()):
            args = trolley.get_status_osc_args()
        # [position, limit, homed, state, calibrated, alarm, alarm_locked,
        #  enabled, speed_pct, dir, accel_time_s, decel_time_s]
        assert len(args) == 12
        assert isinstance(args[0], float)
        assert isinstance(args[3], str)
        assert args[3] == trolley.STATE_IDLE
        assert args[4] == 1
        assert args[5] == 0  # no alarm pin asserted
        assert args[6] == 0  # not latched
        assert args[7] == 1  # enabled
        assert args[8] == pytest.approx(0.3, abs=1e-3)
        assert args[9] == int(trolley.DIR_FORWARD)
        assert args[10] == pytest.approx(0.5)
        assert args[11] == pytest.approx(0.25)

    def test_status_includes_speed_pct_dir_accel_decel(self):
        _reset()
        trolley._current_dir = trolley.DIR_REVERSE
        trolley._accel_time_s = 1.0
        trolley._decel_time_s = 2.0
        max_hz = 1.0 / (2.0 * trolley.TROLLEY_MIN_PULSE_DELAY_S)
        trolley._current_speed_hz = 0.4 * max_hz
        with patch.object(trolley, "GPIO", _make_gpio()):
            s = trolley.get_status()
        assert s["dir"] == int(trolley.DIR_REVERSE)
        assert s["accel_time_s"] == pytest.approx(1.0)
        assert s["decel_time_s"] == pytest.approx(2.0)
        assert s["speed_pct"] == pytest.approx(0.4, abs=1e-3)
        assert s["speed_hz"] == pytest.approx(0.4 * max_hz)

    def test_status_unconfigured_falls_back_to_max_steps(self):
        _reset(calibrated=False)
        s = trolley.get_status()
        assert s["calibrated"] == 0
        assert s["max_steps"] == trolley.TROLLEY_MAX_STEPS
