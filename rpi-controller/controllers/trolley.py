"""Trolley controller: stepper (DIR/PUL/ENA) on a rail with a limit switch.

OSC protocol:

    Raw — for the admin test panel:
      /trolley/enable  int 0|1       enable/disable the driver (ENA is active LOW)
      /trolley/dir     int 0|1       0 = reverse (toward home), 1 = forward
      /trolley/speed   float 0..1    pulse frequency, 0 = stopped, 1 = MIN_PULSE_DELAY_S
      /trolley/step    int           burst N pulses at current speed/dir, aborts on limit
      /trolley/stop                  cancel any burst / position follow
      /trolley/home                  drive reverse until LIM_SWITCH → position = 0

    Position — for timeline playback:
      /trolley/position float 0..1   target position (steps = round(value * TROLLEY_MAX_STEPS))

All motion runs on a single background thread consuming a command queue, so OSC
handlers never block the dispatcher. `_abort_event` short-circuits any ongoing
motion when a new command arrives or when `/trolley/stop` is received.
"""

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

logger = logging.getLogger(__name__)

NAME = "trolley"
STATUS_BROADCAST_ADDRESS = "/trolley/status"
STATUS_BROADCAST_HZ = TROLLEY_STATUS_HZ

DIR_REVERSE = 0  # toward home / limit switch
DIR_FORWARD = 1

# --- state (module-level, parallel to vents) ------------------------------

position_steps = 0         # absolute position, 0 at home
homed = False
limit_error = 0            # 1 while limit switch is HIGH
target_steps = None        # set during position-follow

_current_speed_hz = float(TROLLEY_DEFAULT_SPEED_HZ)
_current_dir = DIR_FORWARD
_enabled = False

last_osc_time = 0.0
_webhooks = None

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
    """Set DIR pin. direction: DIR_FORWARD or DIR_REVERSE."""
    global _current_dir
    _current_dir = DIR_FORWARD if direction else DIR_REVERSE
    GPIO.output(PIN_STEP_DIR, GPIO.HIGH if _current_dir == DIR_FORWARD else GPIO.LOW)


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
        # At home and still driving toward the limit switch → stop.
        return False
    GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
    time.sleep(delay_s)
    GPIO.output(PIN_STEP_PUL, GPIO.LOW)
    time.sleep(delay_s)
    return True


def _apply_step_delta():
    """Increment or decrement position after a successful pulse."""
    global position_steps
    if _current_dir == DIR_FORWARD:
        position_steps += 1
    else:
        position_steps = max(0, position_steps - 1)


def _limit_switch_isr(channel):
    """Called by RPi.GPIO on both edges of LIM_SWITCH. Keep it short."""
    global limit_error, position_steps, homed
    try:
        state = GPIO.input(PIN_LIM_SWITCH)
        if state == GPIO.HIGH:
            limit_error = 1
            # Only treat as home if we were driving toward it.
            if _current_dir == DIR_REVERSE:
                position_steps = 0
                homed = True
                logger.info("Trolley: limit switch hit — position reset to 0")
            else:
                logger.warning("Trolley: limit switch hit while moving forward — check wiring")
        else:
            limit_error = 0
    except Exception as e:
        logger.error("Trolley ISR error: %s", e)


# --- motion thread --------------------------------------------------------

def _motion_loop():
    """Drain command queue; each command aborts any previous motion."""
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
                _run_follow(target, speed_hz)
            elif kind == "home":
                _run_home()
        except Exception as e:
            logger.error("Trolley motion error on %r: %s", cmd, e)
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
    # Adjust target to rail if over-shoot
    target = _clamp(target, 0, TROLLEY_MAX_STEPS)
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
    """Reverse until the limit switch trips (position then forced to 0 by ISR)."""
    global homed
    _set_dir(DIR_REVERSE)
    delay = _speed_to_delay(TROLLEY_DEFAULT_SPEED_HZ)
    # Keep pulsing until the ISR forces position to 0 and sets limit_error.
    while not _abort_event.is_set() and not limit_error:
        if not _pulse_once(delay):
            break
        _apply_step_delta()
    if limit_error:
        homed = True


def _enqueue(cmd):
    """Abort any running motion and submit a new command."""
    _abort_event.set()
    _idle_event.clear()
    _command_queue.put(cmd)


# --- interface ------------------------------------------------------------

def setup(webhooks):
    """Configure pins, start the motion thread, leave driver disabled."""
    global _webhooks, _motion_thread, position_steps, homed, limit_error
    _webhooks = webhooks

    position_steps = 0
    homed = False
    limit_error = 0
    _shutdown_event.clear()
    _abort_event.clear()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Pass initial= so rpi-lgpio (Pi 5) doesn't try to read the pin
    # before claiming it — that fails with 'GPIO not allocated' on a
    # crash-restart where the previous process didn't run cleanup.
    GPIO.setup(PIN_STEP_DIR, GPIO.OUT, initial=GPIO.HIGH)  # default forward
    GPIO.setup(PIN_STEP_PUL, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_STEP_ENA, GPIO.OUT, initial=GPIO.HIGH)  # disabled (active LOW)
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
        "Trolley GPIO: DIR=%d PUL=%d ENA=%d LIM=%d max_steps=%d",
        PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, PIN_LIM_SWITCH, TROLLEY_MAX_STEPS,
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
        GPIO.output(PIN_STEP_ENA, GPIO.HIGH)  # disabled
    except Exception as e:
        logger.error("Trolley cleanup GPIO.output error: %s", e)
    try:
        GPIO.remove_event_detect(PIN_LIM_SWITCH)
    except Exception as e:
        logger.error("Trolley cleanup remove_event_detect error: %s", e)


# --- OSC handlers ---------------------------------------------------------

def _safe(handler_name):
    """Decorator: update last_osc_time, fire webhook on error."""
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
    # Map 0..1 → 0..(1 / (2 * MIN_DELAY)) Hz
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
    logger.info("OSC %s: stop", address)
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
    value = _clamp(float(args[0]), 0.0, 1.0)
    target = int(round(value * TROLLEY_MAX_STEPS))
    logger.info("OSC %s: %.3f → target %d / %d", address, value, target, TROLLEY_MAX_STEPS)
    _set_enable(True)
    _enqueue(("follow", target, _current_speed_hz or TROLLEY_DEFAULT_SPEED_HZ))


def register_osc(dispatcher):
    dispatcher.map("/trolley/enable", handle_enable)
    dispatcher.map("/trolley/dir", handle_dir)
    dispatcher.map("/trolley/speed", handle_speed)
    dispatcher.map("/trolley/step", handle_step)
    dispatcher.map("/trolley/stop", handle_stop)
    dispatcher.map("/trolley/home", handle_home)
    dispatcher.map("/trolley/position", handle_position)


def handle_http_test(body):
    """Direct probe over HTTP — mirrors the OSC surface. body keys:
        command: "enable"|"dir"|"speed"|"step"|"stop"|"home"|"position"
        value:   argument for that command (bool/int/float depending)
    """
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
            _abort_event.set()
        elif command == "home":
            _set_enable(True)
            _enqueue(("home",))
        elif command == "position":
            handle_position("/http", float(value))
        else:
            return {"ok": False, "error": f"unknown command: {command!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "position_steps": position_steps,
        "max_steps": TROLLEY_MAX_STEPS,
        "homed": homed,
        "limit": limit_error,
        "enabled": _enabled,
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
        "max_steps": TROLLEY_MAX_STEPS,
        "position": position_steps,
        "homed": homed,
        "limit": limit_error,
    }


def get_status():
    """Snapshot used by the status broadcaster (see gpio_osc.py)."""
    pos_01 = (position_steps / TROLLEY_MAX_STEPS) if TROLLEY_MAX_STEPS else 0.0
    return {
        "position": _clamp(pos_01, 0.0, 1.0),
        "position_steps": position_steps,
        "max_steps": TROLLEY_MAX_STEPS,
        "limit": int(limit_error),
        "homed": int(homed),
        "enabled": int(_enabled),
    }


def get_status_osc_args():
    """OSC argument list matching /trolley/status (position, limit, homed)."""
    s = get_status()
    return [float(s["position"]), int(s["limit"]), int(s["homed"])]
