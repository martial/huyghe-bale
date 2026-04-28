"""Trolley controller: stepper (DIR/PUL/ENA) on a rail with a limit switch.

OSC protocol:

    Raw — for the admin test panel:
      /trolley/enable  int 0|1       enable/disable the driver (ENA is active LOW)
      /trolley/dir     int 0|1       0 = reverse, 1 = forward (raw DIR pin)
      /trolley/speed   float 0..1    pulse frequency, 0 = stopped, 1 = MIN_PULSE_DELAY_S
      /trolley/step    int           burst N pulses at current speed/dir, aborts on limit
      /trolley/stop                  cancel any burst / position follow / calibration
      /trolley/home                  drive opposite to calibration_direction until LIM_SWITCH

    Calibration:
      /trolley/calibrate/start [dir?]  span the rail at calibration_speed_hz
      /trolley/calibrate/stop          halt + record candidate rail_length_steps
      /trolley/calibrate/save          persist candidate to device.json
      /trolley/calibrate/cancel        discard candidate

    Settings (per-Pi, persisted in device.json):
      /trolley/config/set   key value  validate + stage one field
      /trolley/config/save             persist the staged settings
      /trolley/config/get              broadcast current settings on /trolley/config

    Position — for timeline playback:
      /trolley/position float 0..1   target = round(value * rail_length_steps * soft_limit_pct)
                                     refused if not homed or not calibrated
"""

import json
import logging
import queue
import threading
import time

import RPi.GPIO as GPIO

from config import (
    PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, PIN_LIM_SWITCH,
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

# Semantic directions — independent of which DIR-pin level drives the carriage.
# DIR_FORWARD always means "away from home / limit switch."
# DIR_REVERSE always means "toward home / limit switch."
# The mapping to GPIO HIGH/LOW is decided by the persisted calibration_direction.
DIR_REVERSE = 0
DIR_FORWARD = 1

# State strings broadcast on /trolley/status
STATE_IDLE = "idle"
STATE_HOMING = "homing"
STATE_FOLLOWING = "following"
STATE_CALIBRATING = "calibrating"

CALIBRATION_TIMEOUT_S = 300.0  # safety: auto-cancel a forgotten calibration

# --- runtime settings (loaded from device.json) ---------------------------

_settings: dict = dict(trolley_settings.DEFAULTS)
_settings_pending: dict = {}  # config/set stages here until config/save commits


def _reload_settings():
    """Reload from device.json into module state. Call at boot and after save."""
    global _settings, _settings_pending
    _settings = trolley_settings.load()
    _settings_pending = dict(_settings)


def _rail_length_steps() -> int:
    """Effective MAX_STEPS: the persisted calibration, or the legacy fallback."""
    rail = _settings.get("rail_length_steps")
    return int(rail) if rail else int(TROLLEY_MAX_STEPS)


def _soft_limit_steps() -> int:
    return trolley_settings.soft_limit_steps(_settings)


def _is_calibrated() -> bool:
    return trolley_settings.is_calibrated(_settings)


def _away_pin_high() -> bool:
    """Whether the GPIO DIR pin should be HIGH to drive AWAY from home.

    Encodes calibration_direction. 'forward' → HIGH drives away. 'reverse' → LOW drives away.
    """
    return _settings.get("calibration_direction", "forward") != "reverse"


# --- state (module-level, parallel to vents) ------------------------------

position_steps = 0
homed = False
limit_error = 0
target_steps = None

state = STATE_IDLE
calibration_candidate_steps = None
_calibration_started_at = 0.0

_current_speed_hz = float(TROLLEY_DEFAULT_SPEED_HZ)
_current_dir = DIR_FORWARD
_enabled = False

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
    """Convert speed (Hz) to one half-period (seconds). 0 → slowest allowed."""
    if speed_hz <= 0:
        return TROLLEY_MAX_PULSE_DELAY_S
    delay = 1.0 / (2.0 * speed_hz)
    return _clamp(delay, TROLLEY_MIN_PULSE_DELAY_S, TROLLEY_MAX_PULSE_DELAY_S)


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
        # Already at home and still trying to drive into the switch — stop.
        return False
    GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
    time.sleep(delay_s)
    GPIO.output(PIN_STEP_PUL, GPIO.LOW)
    time.sleep(delay_s)
    return True


def _apply_step_delta():
    """Increment or decrement position after a successful pulse.

    Position is always counted in the calibration frame: forward = away from home,
    reverse = toward home, regardless of which DIR pin level that maps to."""
    global position_steps
    if _current_dir == DIR_FORWARD:
        position_steps += 1
    else:
        position_steps = max(0, position_steps - 1)


def _limit_switch_isr(channel):
    """Called by RPi.GPIO on both edges of LIM_SWITCH. Keep it short."""
    global limit_error, position_steps, homed
    try:
        gpio_state = GPIO.input(PIN_LIM_SWITCH)
        if gpio_state == GPIO.HIGH:
            limit_error = 1
            if _current_dir == DIR_REVERSE:
                # Driving toward home → switch trip = home reached.
                position_steps = 0
                homed = True
                logger.info("Trolley: limit switch hit — position reset to 0")
            else:
                logger.warning("Trolley: limit switch hit while moving away from home — check wiring")
        else:
            limit_error = 0
    except Exception as e:
        logger.error("Trolley ISR error: %s", e)


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
            # Auto-cancel a stuck calibration after timeout
            if state == STATE_CALIBRATING and _calibration_started_at and \
                    (time.time() - _calibration_started_at) > CALIBRATION_TIMEOUT_S:
                logger.warning("Trolley: calibration timed out — auto-cancelling")
                _cancel_calibration()
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
                state = STATE_HOMING
                _run_home()
                state = STATE_IDLE
            elif kind == "calibrate":
                _, speed_hz = cmd
                state = STATE_CALIBRATING
                _run_calibrate(speed_hz)
                # state stays CALIBRATING after the span pass — operator decides
                # save/cancel. _run_calibrate either ran to abort (stop) or limit error.
        except Exception as e:
            logger.error("Trolley motion error on %r: %s", cmd, e)
            state = STATE_IDLE
            if _webhooks:
                _webhooks.fire("error", {"source": "trolley_motion", "error": str(e)})
        finally:
            if _command_queue.empty():
                _idle_event.set()


def _run_step_burst(steps, direction, speed_hz):
    if steps <= 0:
        return
    _set_dir(direction)
    delay = _speed_to_delay(speed_hz)
    for _ in range(steps):
        if not _pulse_once(delay):
            return
        _apply_step_delta()


def _run_follow(target, speed_hz):
    global target_steps
    target_steps = target
    delay = _speed_to_delay(speed_hz)
    target = _clamp(target, 0, _rail_length_steps())
    while not _abort_event.is_set():
        if position_steps == target:
            break
        direction = DIR_FORWARD if target > position_steps else DIR_REVERSE
        if direction != _current_dir:
            _set_dir(direction)
        if not _pulse_once(delay):
            break
        _apply_step_delta()
    target_steps = None


def _run_home():
    """Drive toward the limit switch until ISR resets position to 0."""
    global homed
    _set_dir(DIR_REVERSE)
    delay = _speed_to_delay(TROLLEY_DEFAULT_SPEED_HZ)
    while not _abort_event.is_set() and not limit_error:
        if not _pulse_once(delay):
            break
        _apply_step_delta()
    if limit_error:
        homed = True


def _run_calibrate(speed_hz):
    """Span pass: drive away from home at calibration speed.

    Stops on /trolley/calibrate/stop (which sets _abort_event) or if the limit
    switch unexpectedly trips (wiring inverted)."""
    _set_dir(DIR_FORWARD)
    delay = _speed_to_delay(speed_hz)
    while not _abort_event.is_set():
        if not _pulse_once(delay):
            break
        _apply_step_delta()


def _cancel_calibration():
    global state, calibration_candidate_steps, _calibration_started_at
    _drain_queue()
    _abort_event.set()
    state = STATE_IDLE
    calibration_candidate_steps = None
    _calibration_started_at = 0.0


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
    global _webhooks, _motion_thread, position_steps, homed, limit_error, state
    _webhooks = webhooks
    _reload_settings()

    position_steps = 0
    homed = False
    limit_error = 0
    state = STATE_IDLE
    _shutdown_event.clear()
    _abort_event.clear()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(PIN_STEP_DIR, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(PIN_STEP_PUL, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_STEP_ENA, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(PIN_LIM_SWITCH, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    try:
        GPIO.add_event_detect(
            PIN_LIM_SWITCH, GPIO.BOTH,
            callback=_limit_switch_isr,
            bouncetime=STEP_DEBOUNCE_MS,
        )
    except Exception as e:
        logger.error("Trolley: failed to install limit-switch ISR: %s", e)

    _motion_thread = threading.Thread(target=_motion_loop, name="trolley-motion", daemon=True)
    _motion_thread.start()

    logger.info(
        "Trolley GPIO: DIR=%d PUL=%d ENA=%d LIM=%d rail_length=%d calib_dir=%s calibrated=%s",
        PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, PIN_LIM_SWITCH,
        _rail_length_steps(), _settings.get("calibration_direction"), _is_calibrated(),
    )

    if TROLLEY_AUTO_HOME_ON_BOOT:
        _set_enable(True)
        _enqueue(("home",))


def cleanup():
    """Stop any motion, disable driver, remove ISR."""
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
    try:
        GPIO.remove_event_detect(PIN_LIM_SWITCH)
    except Exception as e:
        logger.error("Trolley cleanup remove_event_detect error: %s", e)


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


@_safe("enable")
def handle_enable(address, *args):
    if not args:
        return
    _set_enable(bool(int(args[0])))
    logger.info("OSC %s: %s", address, "ENABLED" if _enabled else "disabled")


@_safe("dir")
def handle_dir(address, *args):
    if not args:
        return
    _set_dir(int(args[0]))
    logger.info("OSC %s: %s", address, "forward" if _current_dir == DIR_FORWARD else "reverse")


@_safe("speed")
def handle_speed(address, *args):
    global _current_speed_hz
    if not args:
        return
    speed_01 = _clamp(float(args[0]), 0.0, 1.0)
    max_hz = 1.0 / (2.0 * TROLLEY_MIN_PULSE_DELAY_S)
    _current_speed_hz = speed_01 * max_hz
    logger.info("OSC %s: %.3f → %.0f Hz", address, speed_01, _current_speed_hz)


@_safe("step")
def handle_step(address, *args):
    if not args:
        return
    steps = int(args[0])
    if steps <= 0:
        return
    logger.info("OSC %s: %d steps, dir=%d, %.0f Hz", address, steps, _current_dir, _current_speed_hz)
    _enqueue(("step_burst", steps, _current_dir, _current_speed_hz))


@_safe("stop")
def handle_stop(address, *args):
    """Halt motion. During calibration, snapshot the candidate (does not save)."""
    global calibration_candidate_steps
    logger.info("OSC %s: stop", address)
    if state == STATE_CALIBRATING:
        calibration_candidate_steps = position_steps
        logger.info("OSC %s: calibration paused, candidate=%d steps", address, calibration_candidate_steps)
    _drain_queue()
    _abort_event.set()


@_safe("home")
def handle_home(address, *args):
    logger.info("OSC %s: home", address)
    _set_enable(True)
    _enqueue(("home",))


@_safe("position")
def handle_position(address, *args):
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
            logger.warning("OSC %s: refused — trolley not calibrated "
                           "(set permissive_mode=true to override)", address)
            return
    elif not (homed and calibrated):
        logger.warning("OSC %s: PERMISSIVE — homed=%d calibrated=%d, "
                       "using fallback rail=%d steps",
                       address, int(homed), int(calibrated), _rail_length_steps())
    value = _clamp(float(args[0]), 0.0, 1.0)
    # When uncalibrated, _soft_limit_steps() is 0 — fall back to the legacy
    # TROLLEY_MAX_STEPS span so position still scales sensibly for bench tests.
    ceiling = _soft_limit_steps() if calibrated else _rail_length_steps()
    target = int(round(value * ceiling))
    logger.info("OSC %s: %.3f → target %d / %d (rail=%d)",
                address, value, target, ceiling, _rail_length_steps())
    _set_enable(True)
    _enqueue(("follow", target, _current_speed_hz or TROLLEY_DEFAULT_SPEED_HZ))


# Calibration handlers -----------------------------------------------------

@_safe("calibrate_start")
def handle_calibrate_start(address, *args):
    """Span the rail away from home to discover rail_length_steps.

    Optional first arg "forward"|"reverse" updates and persists
    calibration_direction before starting the span pass."""
    global calibration_candidate_steps, _calibration_started_at, position_steps
    if not homed:
        logger.warning("OSC %s: refused — must home before calibrating", address)
        return
    if state == STATE_CALIBRATING:
        logger.info("OSC %s: already calibrating — ignored", address)
        return
    if args:
        candidate = str(args[0]).strip().lower()
        if candidate in trolley_settings.VALID_DIRECTIONS:
            try:
                new_block = dict(_settings)
                new_block["calibration_direction"] = candidate
                trolley_settings.save(new_block)
                _reload_settings()
                logger.info("OSC %s: calibration_direction set to %s", address, candidate)
            except Exception as e:
                logger.warning("OSC %s: failed to persist direction: %s", address, e)
        else:
            logger.warning("OSC %s: ignoring invalid direction %r", address, args[0])
    calibration_candidate_steps = None
    _calibration_started_at = time.time()
    # Reset position frame so the count captured at /calibrate/stop is the rail length.
    position_steps = 0
    logger.info("OSC %s: starting calibration (%s away from home)",
                address, _settings.get("calibration_direction"))
    _set_enable(True)
    _enqueue(("calibrate", _settings.get("calibration_speed_hz")))


@_safe("calibrate_stop")
def handle_calibrate_stop(address, *args):
    """Halt the span pass and record the candidate rail length."""
    global calibration_candidate_steps
    if state != STATE_CALIBRATING:
        logger.info("OSC %s: not calibrating — ignored", address)
        return
    calibration_candidate_steps = position_steps
    logger.info("OSC %s: candidate=%d steps", address, calibration_candidate_steps)
    _drain_queue()
    _abort_event.set()


@_safe("calibrate_save")
def handle_calibrate_save(address, *args):
    """Persist the candidate as rail_length_steps in device.json."""
    global state, calibration_candidate_steps, _calibration_started_at
    if calibration_candidate_steps is None or calibration_candidate_steps <= 0:
        logger.warning("OSC %s: no valid candidate to save", address)
        return
    new_block = dict(_settings)
    new_block["rail_length_steps"] = int(calibration_candidate_steps)
    try:
        trolley_settings.save(new_block)
    except Exception as e:
        logger.error("OSC %s: failed to persist settings: %s", address, e)
        return
    _reload_settings()
    state = STATE_IDLE
    calibration_candidate_steps = None
    _calibration_started_at = 0.0
    logger.info("OSC %s: saved rail_length_steps=%d", address, _settings.get("rail_length_steps"))


@_safe("calibrate_cancel")
def handle_calibrate_cancel(address, *args):
    if state != STATE_CALIBRATING and calibration_candidate_steps is None:
        logger.info("OSC %s: nothing to cancel", address)
        return
    _cancel_calibration()
    logger.info("OSC %s: calibration cancelled", address)


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
        client.send_message("/trolley/config", [json.dumps(_settings)])
    except Exception as e:
        logger.warning("OSC %s: broadcast failed: %s", address, e)


def register_osc(dispatcher):
    dispatcher.map("/trolley/enable", handle_enable)
    dispatcher.map("/trolley/dir", handle_dir)
    dispatcher.map("/trolley/speed", handle_speed)
    dispatcher.map("/trolley/step", handle_step)
    dispatcher.map("/trolley/stop", handle_stop)
    dispatcher.map("/trolley/home", handle_home)
    dispatcher.map("/trolley/position", handle_position)
    dispatcher.map("/trolley/calibrate/start", handle_calibrate_start)
    dispatcher.map("/trolley/calibrate/stop", handle_calibrate_stop)
    dispatcher.map("/trolley/calibrate/save", handle_calibrate_save)
    dispatcher.map("/trolley/calibrate/cancel", handle_calibrate_cancel)
    dispatcher.map("/trolley/config/set", handle_config_set)
    dispatcher.map("/trolley/config/save", handle_config_save)
    dispatcher.map("/trolley/config/get", handle_config_get)


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
        elif command == "step":
            handle_step("/http", int(value))
        elif command == "stop":
            handle_stop("/http")
        elif command == "home":
            handle_home("/http")
        elif command == "position":
            handle_position("/http", float(value))
        elif command == "calibrate_start":
            handle_calibrate_start("/http", value) if value is not None else handle_calibrate_start("/http")
        elif command == "calibrate_stop":
            handle_calibrate_stop("/http")
        elif command == "calibrate_save":
            handle_calibrate_save("/http")
        elif command == "calibrate_cancel":
            handle_calibrate_cancel("/http")
        elif command == "config_set":
            key, val = value or [None, None]
            handle_config_set("/http", key, val)
        elif command == "config_save":
            handle_config_save("/http")
        elif command == "config_get":
            handle_config_get("/http")
        else:
            return {"ok": False, "error": f"unknown command: {command!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "position_steps": position_steps,
        "rail_length_steps": _rail_length_steps(),
        "homed": homed,
        "calibrated": _is_calibrated(),
        "limit": limit_error,
        "enabled": _enabled,
        "state": state,
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
            "limit": PIN_LIM_SWITCH,
        },
        "rail_length_steps": _rail_length_steps(),
        "calibrated": _is_calibrated(),
        "calibration_direction": _settings.get("calibration_direction"),
        "position": position_steps,
        "homed": homed,
        "limit": limit_error,
        "state": state,
    }


def get_status():
    rail = _rail_length_steps()
    pos_01 = (position_steps / rail) if rail else 0.0
    return {
        "position": _clamp(pos_01, 0.0, 1.0),
        "position_steps": position_steps,
        "max_steps": rail,
        "limit": int(limit_error),
        "homed": int(homed),
        "calibrated": int(_is_calibrated()),
        "enabled": int(_enabled),
        "state": state,
        "candidate_steps": int(calibration_candidate_steps) if calibration_candidate_steps else 0,
    }


def get_status_osc_args():
    """OSC argument list for /trolley/status: [position, limit, homed, state, calibrated]."""
    s = get_status()
    return [
        float(s["position"]),
        int(s["limit"]),
        int(s["homed"]),
        str(s["state"]),
        int(s["calibrated"]),
    ]
