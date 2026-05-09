"""Trolley controller: stepper (DIR/PUL/ENA) on a rail with two limit switches.

ENA contract: enable is *always* explicit. /trolley/home, /trolley/position,
and /trolley/step never flip ENA on their own. Caller (admin / bridge / test
panel) is responsible for sending /trolley/enable 1 before motion and
/trolley/enable 0 to release. The one exception is the boot-time auto-home
guarded by TROLLEY_AUTO_HOME_ON_BOOT, which is opt-in and disabled by default.

OSC protocol:

    Raw — for the admin test panel:
      /trolley/enable  int 0|1       enable/disable the driver (ENA is active LOW)
      /trolley/dir     int 0|1       0 = reverse, 1 = forward (raw DIR pin)
      /trolley/speed   float 0..1    pulse frequency, 0 = stopped, 1 = MIN_PULSE_DELAY_S
      /trolley/step    int           burst N pulses at current speed/dir, aborts on limit
      /trolley/stop                  cancel any burst / position follow / homing

    Home — drives until the limit switch in that direction trips:
      /trolley/home  ["reverse"|"forward"|0|1]
                                     omitted/0/"reverse" → toward home end
                                                            (position_steps=0)
                                     "forward"/1         → toward far end
                                                            (position_steps=rail)

    Settings (per-Pi, persisted in device.json):
      /trolley/config/set   key value  validate + stage one field
      /trolley/config/save             persist the staged settings
      /trolley/config/get              broadcast current settings on /trolley/config

    Position — for timeline playback:
      /trolley/position float 0..1   target = round(value * rail_length_steps * soft_limit_pct)
                                     refused if not homed or not configured
"""

import json
import logging
import math
import queue
import threading
import time

import RPi.GPIO as GPIO

from config import (
    PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA,
    PIN_LIM_SWITCH, PIN_LIM_SWITCH_FAR,
    PIN_ALARM_1, PIN_ALARM_2,
    STEP_DEBOUNCE_MS,
    TROLLEY_MAX_STEPS, TROLLEY_MIN_PULSE_DELAY_S, TROLLEY_MAX_PULSE_DELAY_S,
    TROLLEY_DEFAULT_SPEED_HZ, TROLLEY_AUTO_HOME_ON_BOOT,
    TROLLEY_STATUS_HZ,
)
import trolley_settings

logger = logging.getLogger(__name__)

NAME = "trolley"
STATUS_BROADCAST_ADDRESS = "/trolley/status"
STATUS_BROADCAST_HZ = TROLLEY_STATUS_HZ

# Hard safety cap on the /trolley/speed 0..1 input. Even if a client sends 1.0,
# the firmware clamps it here. Also enforced in the admin backend and frontend
# slider, but this is the only enforcement that applies to raw OSC traffic
# (e.g. external bridge messages or scripted clients).
MAX_SPEED_PCT = 0.4

# Semantic directions — independent of which DIR-pin level drives the carriage.
# DIR_FORWARD always means "away from home / toward far limit switch."
# DIR_REVERSE always means "toward home / home limit switch."
# The mapping to GPIO HIGH/LOW is decided by the persisted calibration_direction.
DIR_REVERSE = 0
DIR_FORWARD = 1

# State strings broadcast on /trolley/status
STATE_IDLE = "idle"
STATE_HOMING = "homing"
STATE_FOLLOWING = "following"

# --- runtime settings (loaded from device.json) ---------------------------

_settings: dict = dict(trolley_settings.DEFAULTS)
_settings_pending: dict = {}  # config/set stages here until config/save commits


def _reload_settings():
    """Reload from device.json into module state. Call at boot and after save."""
    global _settings, _settings_pending, _accel_time_s, _decel_time_s
    _settings = trolley_settings.load()
    _settings_pending = dict(_settings)
    _accel_time_s = float(_settings.get("accel_time_s", 0.0) or 0.0)
    _decel_time_s = float(_settings.get("decel_time_s", 0.0) or 0.0)


def _rail_length_steps() -> int:
    """Effective rail length in steps. Uses derived value when configured,
    falls back to TROLLEY_MAX_STEPS for permissive bench testing."""
    derived = trolley_settings.derived_rail_length_steps(_settings)
    return derived if derived else int(TROLLEY_MAX_STEPS)


def _soft_limit_steps() -> int:
    return trolley_settings.soft_limit_steps(_settings)


def _is_calibrated() -> bool:
    return trolley_settings.is_calibrated(_settings)


def _away_pin_high() -> bool:
    """Whether the GPIO DIR pin should be HIGH to drive AWAY from home.

    Encodes calibration_direction. 'forward' → HIGH drives away. 'reverse' → LOW drives away.
    """
    return _settings.get("calibration_direction", "forward") != "reverse"


def _home_pin() -> int:
    """Physical GPIO pin currently acting as the home-end limit switch."""
    if _settings.get("limit_switches_swapped"):
        return PIN_LIM_SWITCH_FAR
    return PIN_LIM_SWITCH


def _far_pin() -> int:
    """Physical GPIO pin currently acting as the far-end limit switch."""
    if _settings.get("limit_switches_swapped"):
        return PIN_LIM_SWITCH
    return PIN_LIM_SWITCH_FAR


# --- state (module-level, parallel to vents) ------------------------------

position_steps = 0
homed = False
limit_error = 0       # home-end switch
far_limit_error = 0   # far-end switch
# Sticky alarm latch: once a driver fault fires, the firmware refuses every
# motion command and disables the driver until the operator explicitly clears
# it via /trolley/alarm/reset (and only if the alarm GPIO has gone LOW again).
alarm_locked = False
target_steps = None

state = STATE_IDLE

_current_speed_hz = float(TROLLEY_DEFAULT_SPEED_HZ)
_current_dir = DIR_FORWARD
_enabled = False

_accel_time_s = 0.0
_decel_time_s = 0.0

last_osc_time = 0.0
_webhooks = None
_pinger_provider = None  # callable returning (ip, port) or None

_command_queue: "queue.Queue" = queue.Queue()
_abort_event = threading.Event()
_shutdown_event = threading.Event()
_idle_event = threading.Event()
_idle_event.set()
_motion_thread: "threading.Thread | None" = None


# --- helpers --------------------------------------------------------------

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _speed_to_delay(speed_hz):
    """Convert speed (Hz) to one half-period (seconds). 0 → slowest allowed.

    Clamps the half-period so the effective frequency never exceeds
    MAX_SPEED_PCT × full firmware bandwidth, regardless of caller. This is the
    last line of defense for the speed cap: home, step, and position-follow
    all funnel through here."""
    if speed_hz <= 0:
        return TROLLEY_MAX_PULSE_DELAY_S
    delay = 1.0 / (2.0 * speed_hz)
    safety_min_delay = TROLLEY_MIN_PULSE_DELAY_S / MAX_SPEED_PCT
    return _clamp(delay, safety_min_delay, TROLLEY_MAX_PULSE_DELAY_S)


def _set_dir(direction):
    """Set DIR pin. direction: DIR_FORWARD (away from home) or DIR_REVERSE (toward home)."""
    global _current_dir
    _current_dir = DIR_FORWARD if direction else DIR_REVERSE
    away_high = _away_pin_high()
    if _current_dir == DIR_FORWARD:
        pin_high = away_high
    else:
        pin_high = not away_high
    GPIO.output(PIN_STEP_DIR, GPIO.HIGH if pin_high else GPIO.LOW)


def _set_enable(on):
    """Set ENA. Active LOW — on=True pulls LOW (enabled)."""
    global _enabled
    _enabled = bool(on)
    GPIO.output(PIN_STEP_ENA, GPIO.LOW if _enabled else GPIO.HIGH)


def _pulse_once(delay_s):
    """One PUL high-low cycle. Returns False if aborted (limit hit or stop)."""
    if _abort_event.is_set():
        return False
    if limit_error and _current_dir == DIR_REVERSE:
        return False
    if far_limit_error and _current_dir == DIR_FORWARD:
        return False
    GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
    time.sleep(delay_s)
    GPIO.output(PIN_STEP_PUL, GPIO.LOW)
    time.sleep(delay_s)
    return True


def _apply_step_delta():
    """Increment or decrement position after a successful pulse.

    Position is always counted in the calibration frame: forward = away from home,
    reverse = toward home, regardless of which DIR pin level that maps to.

    Skipping the delta when the limit-error flag for the current direction is
    already set keeps the count exact when the ISR fires mid-pulse — the ISR
    pins position to its end-stop value, and we don't want to drift past it."""
    global position_steps
    if _current_dir == DIR_FORWARD:
        if far_limit_error:
            return
        position_steps += 1
    else:
        if limit_error:
            return
        position_steps = max(0, position_steps - 1)


def _limit_switch_isr(channel):
    """Home-end limit switch ISR. Fires on both edges. Keep it short."""
    global limit_error, position_steps, homed
    try:
        gpio_state = GPIO.input(_home_pin())
        if gpio_state == GPIO.HIGH:
            limit_error = 1
            if _current_dir == DIR_REVERSE:
                position_steps = 0
                homed = True
                logger.info("Trolley: home switch hit — position reset to 0")
            else:
                logger.warning("Trolley: home switch hit while moving forward — check wiring")
        else:
            limit_error = 0
    except Exception as e:
        logger.error("Trolley home ISR error: %s", e)


def _far_limit_switch_isr(channel):
    """Far-end limit switch ISR. Fires on both edges. Keep it short."""
    global far_limit_error, position_steps, homed
    try:
        gpio_state = GPIO.input(_far_pin())
        if gpio_state == GPIO.HIGH:
            far_limit_error = 1
            if _current_dir == DIR_FORWARD:
                rail = trolley_settings.derived_rail_length_steps(_settings)
                if rail:
                    position_steps = rail
                homed = True
                logger.info("Trolley: far switch hit — position pinned to %d", position_steps)
            else:
                logger.warning("Trolley: far switch hit while moving reverse — check wiring")
        else:
            far_limit_error = 0
    except Exception as e:
        logger.error("Trolley far ISR error: %s", e)


def _alarm_polarity() -> str:
    """One of 'active_high', 'active_low', 'disabled'.

    Defaults to 'disabled' to match trolley_settings.DEFAULTS — the auto-lock
    is opt-in until rig wiring is verified."""
    return _settings.get("alarm_polarity", "disabled")


def _alarm_pin_raw(pin: int) -> int:
    """Raw GPIO level on `pin` (1 = HIGH, 0 = LOW)."""
    try:
        return 1 if GPIO.input(pin) == GPIO.HIGH else 0
    except Exception:
        return 0


def _read_alarm_pins() -> tuple[int, int]:
    """Return interpreted (ALARM_1, ALARM_2) fault flags (1 = fault).

    Interpretation depends on `alarm_polarity`:
      active_high  → fault when GPIO reads HIGH
      active_low   → fault when GPIO reads LOW
      disabled     → always (0, 0)
    """
    pol = _alarm_polarity()
    if pol == "disabled":
        return 0, 0
    raw1 = _alarm_pin_raw(PIN_ALARM_1)
    raw2 = _alarm_pin_raw(PIN_ALARM_2)
    if pol == "active_low":
        return (1 - raw1, 1 - raw2)
    return raw1, raw2


def _alarm_isr(channel):
    """Driver alarm ISR — fires on either ALARM_1 or ALARM_2 edge.

    Latches `alarm_locked` when either pin reports a fault (per
    `alarm_polarity`). Aborts current motion and disables the driver
    immediately. The lock is sticky: even after the pin de-asserts the
    firmware keeps refusing commands until /trolley/alarm/reset is sent."""
    global alarm_locked
    if _alarm_polarity() == "disabled":
        return
    try:
        a1, a2 = _read_alarm_pins()
        if (a1 | a2) and not alarm_locked:
            alarm_locked = True
            _abort_event.set()
            try:
                GPIO.output(PIN_STEP_ENA, GPIO.HIGH)  # active LOW → HIGH disables
            except Exception as e:
                logger.error("Trolley alarm ISR: failed to disable driver: %s", e)
            logger.error(
                "Trolley ALARM latched — driver fault (ALARM_1=%d ALARM_2=%d). "
                "Send /trolley/alarm/reset after clearing the fault.",
                a1, a2,
            )
            if _webhooks:
                _webhooks.fire("alarm", {
                    "source": "trolley", "alarm_1": a1, "alarm_2": a2,
                })
    except Exception as e:
        logger.error("Trolley alarm ISR error: %s", e)


# --- motion thread --------------------------------------------------------

def _motion_loop():
    """Drain command queue; each command aborts any previous motion."""
    global state
    while not _shutdown_event.is_set():
        try:
            cmd = _command_queue.get(timeout=0.1)
        except queue.Empty:
            if _command_queue.empty():
                _idle_event.set()
            continue
        _abort_event.clear()
        try:
            kind = cmd[0]
            if kind == "step_burst":
                _, steps, direction, speed_hz = cmd
                _run_step_burst(steps, direction, speed_hz)
            elif kind == "follow":
                _, target, speed_hz = cmd
                state = STATE_FOLLOWING
                _run_follow(target, speed_hz)
                state = STATE_IDLE
            elif kind == "home":
                _, direction = cmd
                state = STATE_HOMING
                _run_home(direction)
                state = STATE_IDLE
        except Exception as e:
            logger.error("Trolley motion error on %r: %s", cmd, e)
            state = STATE_IDLE
            if _webhooks:
                _webhooks.fire("error", {"source": "trolley_motion", "error": str(e)})
        finally:
            if _command_queue.empty():
                _idle_event.set()


def _run_pulse_train(total_steps, target_hz, accel_s, decel_s):
    """Emit `total_steps` pulses with a trapezoidal velocity profile.

    Direction must be set by the caller. With accel_s == decel_s == 0 this
    falls back to the legacy constant-rate loop (identical wire timing).
    Otherwise: ramp velocity linearly in TIME from 0 → target_hz over
    accel_s seconds (frequency follows √(k/N) over N = target_hz × accel_s / 2
    steps), cruise, then ramp down to 0 over decel_s seconds. If the move is
    too short to fit both ramps, the profile becomes triangular."""
    if total_steps <= 0:
        return

    if accel_s <= 0 and decel_s <= 0:
        delay = _speed_to_delay(target_hz)
        for _ in range(total_steps):
            if not _pulse_once(delay):
                return
            _apply_step_delta()
        return

    # Avg frequency during a 0→target linear ramp is target/2, so the step
    # count for a given ramp time is target_hz * t / 2.
    steps_a = int(target_hz * accel_s / 2) if accel_s > 0 else 0
    steps_d = int(target_hz * decel_s / 2) if decel_s > 0 else 0
    if steps_a + steps_d > total_steps:
        # Triangular profile — scale the two ramps proportionally.
        ramp_total = steps_a + steps_d
        steps_a = int(steps_a * total_steps / ramp_total) if ramp_total else 0
        steps_d = total_steps - steps_a
    steps_c = total_steps - steps_a - steps_d

    for i in range(steps_a):
        f = target_hz * math.sqrt((i + 1) / steps_a)
        if not _pulse_once(_speed_to_delay(f)):
            return
        _apply_step_delta()

    cruise_delay = _speed_to_delay(target_hz)
    for _ in range(steps_c):
        if not _pulse_once(cruise_delay):
            return
        _apply_step_delta()

    for i in range(steps_d):
        f = target_hz * math.sqrt(1.0 - (i + 1) / steps_d)
        if not _pulse_once(_speed_to_delay(f)):
            return
        _apply_step_delta()


def _run_step_burst(steps, direction, speed_hz):
    if steps <= 0:
        return
    _set_dir(direction)
    _run_pulse_train(steps, speed_hz, _accel_time_s, _decel_time_s)


def _run_follow(target, speed_hz):
    global target_steps
    target = _clamp(target, 0, _rail_length_steps())
    target_steps = target
    delta = target - position_steps
    if delta == 0:
        target_steps = None
        return
    direction = DIR_FORWARD if delta > 0 else DIR_REVERSE
    if direction != _current_dir:
        _set_dir(direction)
    _run_pulse_train(abs(delta), speed_hz, _accel_time_s, _decel_time_s)
    target_steps = None


def _run_home(direction):
    """Drive in the requested direction until that end's limit switch trips.

    direction: DIR_REVERSE → toward home switch, DIR_FORWARD → toward far switch."""
    _set_dir(direction)
    speed = float(_settings.get("home_speed_hz") or TROLLEY_DEFAULT_SPEED_HZ)
    delay = _speed_to_delay(speed)
    if direction == DIR_FORWARD:
        while not _abort_event.is_set() and not far_limit_error:
            if not _pulse_once(delay):
                break
            _apply_step_delta()
    else:
        while not _abort_event.is_set() and not limit_error:
            if not _pulse_once(delay):
                break
            _apply_step_delta()


def _drain_queue():
    while not _command_queue.empty():
        try:
            _command_queue.get_nowait()
        except queue.Empty:
            break


def _enqueue(cmd):
    """Abort any running motion and submit a new command."""
    _abort_event.set()
    _idle_event.clear()
    _command_queue.put(cmd)


# --- interface ------------------------------------------------------------

def setup(webhooks):
    """Configure pins, start the motion thread, leave driver disabled."""
    global _webhooks, _motion_thread, position_steps, homed, limit_error, far_limit_error, state
    global alarm_locked
    _webhooks = webhooks
    _reload_settings()

    position_steps = 0
    homed = False
    limit_error = 0
    far_limit_error = 0
    alarm_locked = False
    state = STATE_IDLE
    _shutdown_event.clear()
    _abort_event.clear()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(PIN_STEP_DIR, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(PIN_STEP_PUL, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_STEP_ENA, GPIO.OUT, initial=GPIO.HIGH)
    home_pin = _home_pin()
    far_pin = _far_pin()
    GPIO.setup(home_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(far_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_ALARM_1, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_ALARM_2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    try:
        GPIO.add_event_detect(
            home_pin, GPIO.BOTH,
            callback=_limit_switch_isr,
            bouncetime=STEP_DEBOUNCE_MS,
        )
    except Exception as e:
        logger.error("Trolley: failed to install home-switch ISR: %s", e)

    try:
        GPIO.add_event_detect(
            far_pin, GPIO.BOTH,
            callback=_far_limit_switch_isr,
            bouncetime=STEP_DEBOUNCE_MS,
        )
    except Exception as e:
        logger.error("Trolley: failed to install far-switch ISR: %s", e)

    for alarm_pin in (PIN_ALARM_1, PIN_ALARM_2):
        try:
            GPIO.add_event_detect(
                alarm_pin, GPIO.BOTH,
                callback=_alarm_isr,
                bouncetime=STEP_DEBOUNCE_MS,
            )
        except Exception as e:
            logger.error("Trolley: failed to install alarm ISR on %d: %s", alarm_pin, e)

    # If the rig already has an alarm asserted at boot, latch the lock now so
    # we don't enable the driver into a known-bad state.
    a1, a2 = _read_alarm_pins()
    if a1 | a2:
        alarm_locked = True
        logger.error("Trolley: alarm asserted at boot (ALARM_1=%d ALARM_2=%d) — locked", a1, a2)

    _motion_thread = threading.Thread(target=_motion_loop, name="trolley-motion", daemon=True)
    _motion_thread.start()

    logger.info(
        "Trolley GPIO: DIR=%d PUL=%d ENA=%d LIM_HOME=%d LIM_FAR=%d rail_length=%d calib_dir=%s swapped=%s configured=%s",
        PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, home_pin, far_pin,
        _rail_length_steps(), _settings.get("calibration_direction"),
        bool(_settings.get("limit_switches_swapped")), _is_calibrated(),
    )

    if TROLLEY_AUTO_HOME_ON_BOOT:
        _set_enable(True)
        _enqueue(("home", DIR_REVERSE))


def cleanup():
    """Stop any motion, disable driver, remove ISRs."""
    logger.info("Trolley shutdown — aborting motion and disabling driver")
    _abort_event.set()
    _shutdown_event.set()
    if _motion_thread is not None:
        _motion_thread.join(timeout=1.0)
    try:
        GPIO.output(PIN_STEP_PUL, GPIO.LOW)
        GPIO.output(PIN_STEP_ENA, GPIO.HIGH)
    except Exception as e:
        logger.error("Trolley cleanup GPIO.output error: %s", e)
    for pin in (_home_pin(), _far_pin(), PIN_ALARM_1, PIN_ALARM_2):
        try:
            GPIO.remove_event_detect(pin)
        except Exception as e:
            logger.error("Trolley cleanup remove_event_detect(%d) error: %s", pin, e)


def set_pinger_provider(provider):
    """Inject a callable used by /trolley/config/get to resolve where to broadcast."""
    global _pinger_provider
    _pinger_provider = provider


# --- OSC handlers ---------------------------------------------------------

def _safe(handler_name):
    def deco(fn):
        def wrapped(address, *args):
            global last_osc_time
            last_osc_time = time.time()
            try:
                fn(address, *args)
            except Exception as e:
                logger.error("Handler error on %s: %s", address, e)
                if _webhooks:
                    _webhooks.fire("error", {"source": "osc_handler", "handler": handler_name, "error": str(e)})
        return wrapped
    return deco


def _alarm_blocks(address: str) -> bool:
    """If the alarm lock is latched, refuse this command and log it.

    Returns True when the caller should bail out. Stop, config_*, and
    alarm_reset bypass this check (they're either safe or the way to recover)."""
    if alarm_locked:
        logger.warning("OSC %s: refused — alarm latched. Send /trolley/alarm/reset.",
                       address)
        return True
    return False


@_safe("enable")
def handle_enable(address, *args):
    if _alarm_blocks(address):
        return
    if not args:
        return
    _set_enable(bool(int(args[0])))
    logger.info("OSC %s: %s", address, "ENABLED" if _enabled else "disabled")


@_safe("dir")
def handle_dir(address, *args):
    if _alarm_blocks(address):
        return
    if not args:
        return
    _set_dir(int(args[0]))
    logger.info("OSC %s: %s", address, "forward" if _current_dir == DIR_FORWARD else "reverse")


@_safe("speed")
def handle_speed(address, *args):
    global _current_speed_hz
    if _alarm_blocks(address):
        return
    if not args:
        return
    raw = float(args[0])
    speed_01 = _clamp(raw, 0.0, MAX_SPEED_PCT)
    max_hz = 1.0 / (2.0 * TROLLEY_MIN_PULSE_DELAY_S)
    _current_speed_hz = speed_01 * max_hz
    if raw > MAX_SPEED_PCT:
        logger.warning("OSC %s: %.3f exceeds safety cap %.2f, clamped",
                       address, raw, MAX_SPEED_PCT)
    logger.info("OSC %s: %.3f → %.0f Hz", address, speed_01, _current_speed_hz)


@_safe("accel")
def handle_accel(address, *args):
    """Set the linear ramp-up time (seconds) used by /trolley/step and /trolley/position.
    Also stages the value in _settings_pending so a subsequent
    /trolley/config/save will persist it across reboots."""
    global _accel_time_s
    if _alarm_blocks(address):
        return
    if not args:
        return
    _accel_time_s = _clamp(float(args[0]), 0.0, 10.0)
    _settings_pending["accel_time_s"] = _accel_time_s
    logger.info("OSC %s: accel_time_s=%.3f", address, _accel_time_s)


@_safe("decel")
def handle_decel(address, *args):
    """Set the linear ramp-down time (seconds) used by /trolley/step and /trolley/position.
    Also stages the value in _settings_pending so a subsequent
    /trolley/config/save will persist it across reboots."""
    global _decel_time_s
    if _alarm_blocks(address):
        return
    if not args:
        return
    _decel_time_s = _clamp(float(args[0]), 0.0, 10.0)
    _settings_pending["decel_time_s"] = _decel_time_s
    logger.info("OSC %s: decel_time_s=%.3f", address, _decel_time_s)


@_safe("step")
def handle_step(address, *args):
    if _alarm_blocks(address):
        return
    if not args:
        return
    steps = int(args[0])
    if steps <= 0:
        return
    logger.info("OSC %s: %d steps, dir=%d, %.0f Hz", address, steps, _current_dir, _current_speed_hz)
    _enqueue(("step_burst", steps, _current_dir, _current_speed_hz))


@_safe("stop")
def handle_stop(address, *args):
    """Halt motion."""
    logger.info("OSC %s: stop", address)
    _drain_queue()
    _abort_event.set()


def _parse_direction(value, default=DIR_REVERSE):
    """Parse a direction OSC arg into DIR_FORWARD/DIR_REVERSE.

    Accepts "forward"/"reverse" strings, or 0/1 ints. Empty/None/0 → default."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("forward", "fwd", "1"):
            return DIR_FORWARD
        if s in ("reverse", "rev", "0", ""):
            return DIR_REVERSE
        return default
    try:
        return DIR_FORWARD if int(value) else DIR_REVERSE
    except (TypeError, ValueError):
        return default


@_safe("home")
def handle_home(address, *args):
    if _alarm_blocks(address):
        return
    direction = _parse_direction(args[0] if args else None, default=DIR_REVERSE)
    logger.info("OSC %s: home %s", address, "forward" if direction == DIR_FORWARD else "reverse")
    _enqueue(("home", direction))


@_safe("position")
def handle_position(address, *args):
    if _alarm_blocks(address):
        return
    if not args:
        return
    permissive = bool(_settings.get("permissive_mode", True))
    calibrated = _is_calibrated()
    if not permissive:
        if not homed:
            logger.warning("OSC %s: refused — trolley not homed "
                           "(set permissive_mode=true to override)", address)
            return
        if not calibrated:
            logger.warning("OSC %s: refused — trolley not configured "
                           "(set permissive_mode=true to override)", address)
            return
    elif not (homed and calibrated):
        logger.warning("OSC %s: PERMISSIVE — homed=%d configured=%d, "
                       "using fallback rail=%d steps",
                       address, int(homed), int(calibrated), _rail_length_steps())
    value = _clamp(float(args[0]), 0.0, 1.0)
    # When unconfigured, _soft_limit_steps() is 0 — fall back to the
    # _rail_length_steps() (which uses TROLLEY_MAX_STEPS in that case)
    # so position still scales sensibly for bench tests.
    ceiling = _soft_limit_steps() if calibrated else _rail_length_steps()
    target = int(round(value * ceiling))
    logger.info("OSC %s: %.3f → target %d / %d (rail=%d)",
                address, value, target, ceiling, _rail_length_steps())
    _enqueue(("follow", target, _current_speed_hz or TROLLEY_DEFAULT_SPEED_HZ))


# Settings handlers --------------------------------------------------------

@_safe("config_set")
def handle_config_set(address, *args):
    """Stage one setting in memory. Persist with /trolley/config/save."""
    if len(args) < 2:
        logger.warning("OSC %s: needs (key, value)", address)
        return
    key = str(args[0])
    if key not in trolley_settings.ALLOWED_KEYS:
        logger.warning("OSC %s: unknown key %r", address, key)
        return
    try:
        value = trolley_settings.update(key, args[1])
    except Exception as e:
        logger.warning("OSC %s: invalid %s=%r: %s", address, key, args[1], e)
        return
    _settings_pending[key] = value
    logger.info("OSC %s: staged %s=%r", address, key, value)


@_safe("config_save")
def handle_config_save(address, *args):
    """Persist staged settings to device.json and reload."""
    try:
        trolley_settings.save(_settings_pending)
    except Exception as e:
        logger.error("OSC %s: failed to persist: %s", address, e)
        return
    _reload_settings()
    logger.info("OSC %s: settings saved", address)


@_safe("alarm_reset")
def handle_alarm_reset(address, *args):
    """Clear the latched alarm lock — only succeeds if both ALARM pins are LOW.

    Use after the operator has cleared the underlying driver fault (per the
    CL86Y manual: power cycle for overcurrent / phase / encoder errors;
    auto-recover for over/undervoltage; pulse ENA low for over-tolerance)."""
    global alarm_locked
    a1, a2 = _read_alarm_pins()
    if a1 | a2:
        logger.warning("OSC %s: cannot reset, alarm still active "
                       "(ALARM_1=%d ALARM_2=%d)", address, a1, a2)
        return
    if alarm_locked:
        alarm_locked = False
        logger.info("OSC %s: alarm cleared, motion re-armed", address)


@_safe("config_get")
def handle_config_get(address, *args):
    """Broadcast the current settings as a single JSON-encoded /trolley/config message."""
    if _pinger_provider is None:
        logger.debug("OSC %s: no pinger to reply to", address)
        return
    target = _pinger_provider()
    if not target:
        return
    ip, port = target
    try:
        from pythonosc.udp_client import SimpleUDPClient
        client = SimpleUDPClient(ip, port)
        payload = dict(_settings)
        payload["rail_length_steps"] = trolley_settings.derived_rail_length_steps(_settings)
        client.send_message("/trolley/config", [json.dumps(payload)])
    except Exception as e:
        logger.warning("OSC %s: broadcast failed: %s", address, e)


def register_osc(dispatcher):
    dispatcher.map("/trolley/enable", handle_enable)
    dispatcher.map("/trolley/dir", handle_dir)
    dispatcher.map("/trolley/speed", handle_speed)
    dispatcher.map("/trolley/accel", handle_accel)
    dispatcher.map("/trolley/decel", handle_decel)
    dispatcher.map("/trolley/step", handle_step)
    dispatcher.map("/trolley/stop", handle_stop)
    dispatcher.map("/trolley/home", handle_home)
    dispatcher.map("/trolley/position", handle_position)
    dispatcher.map("/trolley/config/set", handle_config_set)
    dispatcher.map("/trolley/config/save", handle_config_save)
    dispatcher.map("/trolley/config/get", handle_config_get)
    dispatcher.map("/trolley/alarm/reset", handle_alarm_reset)


def handle_http_test(body):
    """Direct probe over HTTP — mirrors the OSC surface."""
    command = (body or {}).get("command")
    value = (body or {}).get("value")
    try:
        if command == "enable":
            _set_enable(bool(int(value)))
        elif command == "dir":
            _set_dir(int(value))
        elif command == "speed":
            handle_speed("/http", float(value))
        elif command == "accel":
            handle_accel("/http", float(value))
        elif command == "decel":
            handle_decel("/http", float(value))
        elif command == "step":
            handle_step("/http", int(value))
        elif command == "stop":
            handle_stop("/http")
        elif command == "home":
            handle_home("/http", value) if value is not None else handle_home("/http")
        elif command == "position":
            handle_position("/http", float(value))
        elif command == "config_set":
            key, val = value or [None, None]
            handle_config_set("/http", key, val)
        elif command == "config_save":
            handle_config_save("/http")
        elif command == "alarm_reset":
            handle_alarm_reset("/http")
        elif command == "config_get":
            # Return the full settings dict in the HTTP response so the admin
            # frontend can read back the persisted config without OSC plumbing.
            payload = dict(_settings)
            payload["rail_length_steps"] = trolley_settings.derived_rail_length_steps(_settings)
            return {
                "ok": True,
                "config": payload,
                "position_steps": position_steps,
                "homed": homed,
                "calibrated": _is_calibrated(),
                "limit": limit_error,
                "far_limit": far_limit_error,
                "enabled": _enabled,
                "state": state,
            }
        else:
            return {"ok": False, "error": f"unknown command: {command!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    a1, a2 = _read_alarm_pins()
    return {
        "ok": True,
        "position_steps": position_steps,
        "rail_length_steps": _rail_length_steps(),
        "homed": homed,
        "calibrated": _is_calibrated(),
        "limit": limit_error,
        "far_limit": far_limit_error,
        "enabled": _enabled,
        "state": state,
        "alarm": int(a1 | a2),
        "alarm_1": int(a1),
        "alarm_2": int(a2),
        "alarm_1_raw": _alarm_pin_raw(PIN_ALARM_1),
        "alarm_2_raw": _alarm_pin_raw(PIN_ALARM_2),
        "alarm_polarity": _alarm_polarity(),
        "alarm_locked": bool(alarm_locked),
    }


def get_last_osc_time():
    return last_osc_time


def describe():
    return {
        "controller": NAME,
        "pins": {
            "dir": PIN_STEP_DIR,
            "pul": PIN_STEP_PUL,
            "ena": PIN_STEP_ENA,
            "limit": _home_pin(),
            "limit_far": _far_pin(),
        },
        "rail_length_steps": _rail_length_steps(),
        "calibrated": _is_calibrated(),
        "calibration_direction": _settings.get("calibration_direction"),
        "limit_switches_swapped": bool(_settings.get("limit_switches_swapped")),
        "position": position_steps,
        "homed": homed,
        "limit": limit_error,
        "far_limit": far_limit_error,
        "state": state,
    }


def get_status():
    rail = _rail_length_steps()
    pos_01 = (position_steps / rail) if rail else 0.0
    a1, a2 = _read_alarm_pins()
    max_hz = 1.0 / (2.0 * TROLLEY_MIN_PULSE_DELAY_S)
    speed_pct = (_current_speed_hz / max_hz) if max_hz else 0.0
    return {
        "position": _clamp(pos_01, 0.0, 1.0),
        "position_steps": position_steps,
        "max_steps": rail,
        "limit": int(limit_error),
        "far_limit": int(far_limit_error),
        "homed": int(homed),
        "calibrated": int(_is_calibrated()),
        "enabled": int(_enabled),
        "state": state,
        "accel_time_s": _accel_time_s,
        "decel_time_s": _decel_time_s,
        "speed_pct": _clamp(speed_pct, 0.0, 1.0),
        "speed_hz": _current_speed_hz,
        "dir": int(_current_dir),
        "alarm": int(a1 | a2),
        "alarm_1": int(a1),
        "alarm_2": int(a2),
        "alarm_1_raw": _alarm_pin_raw(PIN_ALARM_1),
        "alarm_2_raw": _alarm_pin_raw(PIN_ALARM_2),
        "alarm_polarity": _alarm_polarity(),
        "alarm_locked": int(alarm_locked),
    }


def get_status_osc_args():
    """OSC argument list for /trolley/status:
    [position, limit, homed, state, calibrated, alarm, alarm_locked, enabled,
     speed_pct, dir, accel_time_s, decel_time_s].

    Older admin receivers ignore trailing fields; new ones decode them. The
    `enabled` flag reflects the live ENA state so the admin checkbox can sync
    after a page reload. `speed_pct`, `dir`, `accel_time_s`, `decel_time_s`
    let the admin echo live driver state next to its editable controls."""
    s = get_status()
    return [
        float(s["position"]),
        int(s["limit"]),
        int(s["homed"]),
        str(s["state"]),
        int(s["calibrated"]),
        int(s["alarm"]),
        int(s["alarm_locked"]),
        int(s["enabled"]),
        float(s["speed_pct"]),
        int(s["dir"]),
        float(s["accel_time_s"]),
        float(s["decel_time_s"]),
    ]
