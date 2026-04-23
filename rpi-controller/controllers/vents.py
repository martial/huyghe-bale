"""Vents controller: 3 Peltier cells + 2 PWM fans + 4 tachos + 2 DS18B20 temps.

Hardware:
  - Three Peltier stacks on GPIO {26, 25, 24}, digital on/off (active HIGH).
    Each thermoelectric module has a cold face and a hot face; when ON, heat is
    pumped from one side to the other (physics of the install determines which
    face faces the conditioned volume).
  - Fan 1 — cold-side ventilation PWM on GPIO 20; fan 2 — hot-side PWM on GPIO 18.
  - Tachos on GPIO {27, 17, 23, 22} (pair A/B per fan), falling-edge ISR
    → period → RPM.
  - Two DS18B20 probes on 1-wire (`dtoverlay=w1-gpio` in config.txt). Typically
    one probe tracks the cold path and one the hot path; discovery order maps to
    temp1_c / temp2_c. Auto regulation uses their average unless both are missing.

Temperature control — two independent concepts:

  - **target** (+ hysteresis): regulation setpoint vs **average** probe temperature.
    Bang-bang: below target − H → all cells **ON** (heat pumping active); above
    target + H (and under max) → all **OFF**; in band → **holding**. State names
    heating/cooling describe whether cells are driven, not which Peltier face is
    physically hot or cold. Fans are not used for this loop (use raw or /vents/fan/*).
  - **max_temp_c**: **safety** ceiling (persisted on the Pi). If avg temp exceeds
    max, state is "over_temp": all Peltiers off; fan PWM is left unchanged (auto
    does not touch fans for over_temp either).
    Peltier "on" commands are ignored while above max (interlock).

OSC protocol:

  Raw commands (admin → Pi on port 9000):
    /vents/peltier/1  int 0|1
    /vents/peltier/2  int 0|1
    /vents/peltier/3  int 0|1
    /vents/peltier    int mask  (bit 0 = P1, bit 1 = P2, bit 2 = P3)
    /vents/fan/1      float 0..1
    /vents/fan/2      float 0..1
    /vents/mode       string "raw" | "auto"
    /vents/target     float target temperature in °C (setpoint for Peltier regulation)
    /vents/max_temp   float safety max °C (stored in ~/.config/gpio-osc/vents_prefs.json)

  Status broadcast (Pi → admin on port 9001) every VENTS_STATUS_HZ ticks:
    /vents/status temp1, temp2, fan1_0_1, fan2_0_1, peltier_mask,
                  rpm1A, rpm1B, rpm2A, rpm2B, target_c, mode, state, max_temp_c

Auto loop: avg > max → over_temp (Peltiers off only). avg < target − H → heating
(mask 0b111). avg > target + H (and ≤ max) → cooling (mask 0). else → holding.
Missing sensors → sensor_error (Peltiers + fans off).
"""

import glob
import json
import logging
import os
import threading
import time
from pathlib import Path

import RPi.GPIO as GPIO

from config import (
    PIN_PELTIER_1, PIN_PELTIER_2, PIN_PELTIER_3,
    PIN_PWM_FAN_1, PIN_PWM_FAN_2,
    PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B,
    PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B,
    VENTS_FAN_PWM_FREQ,
    VENTS_FAN_PWM_MIN_PCT, VENTS_FAN_PWM_MAX_PCT,
    VENTS_DEFAULT_TARGET_C, VENTS_HYSTERESIS_C, VENTS_DEFAULT_MAX_TEMP_C,
    VENTS_AUTO_LOOP_HZ,
    VENTS_TEMP_POLL_HZ, VENTS_TACHO_MIN_DT_S,
    VENTS_STATUS_HZ,
)

logger = logging.getLogger(__name__)

NAME = "vents"
STATUS_BROADCAST_ADDRESS = "/vents/status"
STATUS_BROADCAST_HZ = VENTS_STATUS_HZ

PELTIER_PINS = (PIN_PELTIER_1, PIN_PELTIER_2, PIN_PELTIER_3)

_PREFS_PATH = Path(os.path.expanduser("~/.config/gpio-osc/vents_prefs.json"))
# Keep max_temp_c strictly above the upper regulation edge (target + H).
_BAND_MARGIN_C = 0.05

# ── state (module-level, read by OSC/HTTP handlers + status broadcaster) ──

pwm_fan_1 = None
pwm_fan_2 = None
fan_duty = [VENTS_FAN_PWM_MIN_PCT, VENTS_FAN_PWM_MIN_PCT]  # indices 0, 1 for fan 1/2
peltier_state = [0, 0, 0]

tacho_last_t = [0.0, 0.0, 0.0, 0.0]  # 1A, 1B, 2A, 2B
tacho_rpm = [0.0, 0.0, 0.0, 0.0]

temp_c = [None, None]  # temp1, temp2
_temp_files = [None, None]  # paths to DS18B20 w1_slave files, None if sensor missing

target_temp_c = float(VENTS_DEFAULT_TARGET_C)
max_temp_c = float(VENTS_DEFAULT_MAX_TEMP_C)  # over-temp threshold; persisted in _PREFS_PATH
mode = "raw"          # "raw" or "auto"
state = "idle"        # idle|heating|cooling|holding|sensor_error|over_temp

last_osc_time = 0.0
_webhooks = None

_shutdown_event = threading.Event()
_auto_thread = None
_temp_thread = None


# ── helpers ───────────────────────────────────────────────────────────────

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _regulation_band_high():
    return target_temp_c + VENTS_HYSTERESIS_C


def _min_allowed_max_temp_c():
    return _regulation_band_high() + _BAND_MARGIN_C


def _clamp_target_vs_max():
    """Ensure target band stays strictly below max_temp_c."""
    global target_temp_c
    ceiling = max_temp_c - VENTS_HYSTERESIS_C - _BAND_MARGIN_C
    if target_temp_c > ceiling:
        logger.warning(
            "target clamped from %.2f °C to %.2f °C so band stays below max_temp_c (%.2f)",
            target_temp_c,
            ceiling,
            max_temp_c,
        )
        target_temp_c = ceiling


def _clamp_max_vs_target():
    """Ensure max_temp_c stays strictly above regulation band upper edge."""
    global max_temp_c
    lo = _min_allowed_max_temp_c()
    if max_temp_c <= lo:
        logger.warning(
            "max_temp_c raised from %.2f °C to %.2f °C (must exceed target + hysteresis)",
            max_temp_c,
            lo,
        )
        max_temp_c = lo


def _load_prefs():
    """Load max_temp_c from disk (called from setup)."""
    global max_temp_c
    try:
        data = json.loads(_PREFS_PATH.read_text())
        v = float(data.get("max_temp_c", VENTS_DEFAULT_MAX_TEMP_C))
        max_temp_c = _clamp(v, -55.0, 125.0)
        _clamp_max_vs_target()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Failed to load vents prefs from %s: %s", _PREFS_PATH, e)


def _save_prefs():
    """Persist max_temp_c for reboot."""
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PREFS_PATH.with_suffix(".json.tmp")
        payload = json.dumps({"max_temp_c": max_temp_c}, indent=2) + "\n"
        tmp.write_text(payload)
        tmp.replace(_PREFS_PATH)
    except Exception as e:
        logger.error("Failed to save vents prefs to %s: %s", _PREFS_PATH, e)


def _set_max_temp_c(value):
    """Set absolute over-temperature threshold (°C) and persist."""
    global max_temp_c
    max_temp_c = _clamp(float(value), -55.0, 125.0)
    _clamp_max_vs_target()
    _save_prefs()
    logger.info("Vents max temperature threshold → %.2f °C (saved)", max_temp_c)


def _set_peltier(index, on):
    """index is 0..2 (pin 26/25/24)."""
    pin = PELTIER_PINS[index]
    GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
    peltier_state[index] = 1 if on else 0


def _set_fan(index, duty_0_1):
    """index is 0 (fan 1) or 1 (fan 2). duty_0_1 in [0, 1]."""
    duty_pct = _clamp(float(duty_0_1) * 100.0,
                      VENTS_FAN_PWM_MIN_PCT if duty_0_1 > 0 else 0.0,
                      VENTS_FAN_PWM_MAX_PCT)
    if index == 0 and pwm_fan_1 is not None:
        pwm_fan_1.ChangeDutyCycle(duty_pct)
    elif index == 1 and pwm_fan_2 is not None:
        pwm_fan_2.ChangeDutyCycle(duty_pct)
    fan_duty[index] = duty_pct


def _peltier_mask():
    return peltier_state[0] | (peltier_state[1] << 1) | (peltier_state[2] << 2)


def _apply_peltier_mask(mask):
    for i in range(3):
        _set_peltier(i, bool(mask & (1 << i)))


# ── DS18B20 temperature sensors ───────────────────────────────────────────

def _discover_sensors():
    """Locate up to two /sys/bus/w1/devices/28*/w1_slave files. Missing
    sensors are tolerated: the corresponding entry stays None and the
    broadcaster reports null temps. Auto mode will refuse to run."""
    base = "/sys/bus/w1/devices/"
    try:
        found = sorted(glob.glob(base + "28*"))
    except Exception as e:
        logger.warning("Temp sensor discovery failed: %s", e)
        return
    for i, folder in enumerate(found[:2]):
        _temp_files[i] = os.path.join(folder, "w1_slave")
        logger.info("DS18B20 sensor %d → %s", i + 1, _temp_files[i])
    if not found:
        logger.warning("No DS18B20 sensors found. Check dtoverlay=w1-gpio in config.txt.")


def _read_ds18b20(path):
    """Read one temperature in °C. Returns None on parse failure."""
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        if not lines or lines[0].strip()[-3:] != "YES":
            return None
        eq = lines[1].find("t=")
        if eq < 0:
            return None
        return float(lines[1][eq + 2:]) / 1000.0
    except Exception as e:
        logger.debug("DS18B20 read error on %s: %s", path, e)
        return None


def _temp_loop():
    """Poll both sensors at VENTS_TEMP_POLL_HZ."""
    period = 1.0 / max(1, VENTS_TEMP_POLL_HZ)
    while not _shutdown_event.is_set():
        for i in range(2):
            if _temp_files[i]:
                temp_c[i] = _read_ds18b20(_temp_files[i])
        _shutdown_event.wait(period)


# ── tacho ISRs ────────────────────────────────────────────────────────────

def _make_tacho_cb(idx):
    def _cb(channel):
        now = time.time()
        dt = now - tacho_last_t[idx]
        if dt < VENTS_TACHO_MIN_DT_S:
            return
        tacho_rpm[idx] = (1.0 / dt) / 2.0 * 60.0  # 2 pulses per revolution
        tacho_last_t[idx] = now
    return _cb


def _tacho_decay_tick():
    """If a fan stops, no falling edges arrive and tacho_rpm stays stale.
    Zero out readings that haven't updated within a reasonable window."""
    now = time.time()
    stale = 2.0  # seconds
    for i in range(4):
        if tacho_last_t[i] and (now - tacho_last_t[i]) > stale:
            tacho_rpm[i] = 0.0


# ── auto-regulation loop ──────────────────────────────────────────────────

def _avg_temp():
    vals = [t for t in temp_c if t is not None]
    return sum(vals) / len(vals) if vals else None


def _over_temp_interlock():
    """True when average temp is above max_temp_c (same test as auto hot branch)."""
    avg = _avg_temp()
    if avg is None:
        return False
    return avg > max_temp_c


def _auto_loop():
    global state
    period = 1.0 / max(1, VENTS_AUTO_LOOP_HZ)
    while not _shutdown_event.is_set():
        if mode == "auto":
            avg = _avg_temp()
            if avg is None:
                if state != "sensor_error":
                    logger.warning("Auto mode active but no valid temperature — halting peltiers")
                state = "sensor_error"
                _apply_peltier_mask(0)
                _set_fan(0, 0.0)
                _set_fan(1, 0.0)
            elif avg > max_temp_c:
                state = "over_temp"
                _apply_peltier_mask(0)
            elif avg < target_temp_c - VENTS_HYSTERESIS_C:
                state = "heating"
                _apply_peltier_mask(0b111)
            elif avg > target_temp_c + VENTS_HYSTERESIS_C:
                state = "cooling"
                _apply_peltier_mask(0)
            else:
                state = "holding"
                # deadband — keep previous Peltier outputs; fans unchanged by auto
        else:
            state = "idle"
        _tacho_decay_tick()
        _shutdown_event.wait(period)


# ── interface ─────────────────────────────────────────────────────────────

def setup(webhooks):
    global _webhooks, pwm_fan_1, pwm_fan_2, _auto_thread, _temp_thread
    _webhooks = webhooks

    _shutdown_event.clear()
    _load_prefs()
    _clamp_max_vs_target()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for pin in PELTIER_PINS:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

    GPIO.setup(PIN_PWM_FAN_1, GPIO.OUT)
    GPIO.setup(PIN_PWM_FAN_2, GPIO.OUT)
    pwm_fan_1 = GPIO.PWM(PIN_PWM_FAN_1, VENTS_FAN_PWM_FREQ)
    pwm_fan_2 = GPIO.PWM(PIN_PWM_FAN_2, VENTS_FAN_PWM_FREQ)
    pwm_fan_1.start(VENTS_FAN_PWM_MIN_PCT)
    pwm_fan_2.start(VENTS_FAN_PWM_MIN_PCT)
    fan_duty[0] = VENTS_FAN_PWM_MIN_PCT
    fan_duty[1] = VENTS_FAN_PWM_MIN_PCT

    for pin in (PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B, PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    try:
        GPIO.add_event_detect(PIN_TACHO_FAN_1A, GPIO.FALLING, callback=_make_tacho_cb(0))
        GPIO.add_event_detect(PIN_TACHO_FAN_1B, GPIO.FALLING, callback=_make_tacho_cb(1))
        GPIO.add_event_detect(PIN_TACHO_FAN_2A, GPIO.FALLING, callback=_make_tacho_cb(2))
        GPIO.add_event_detect(PIN_TACHO_FAN_2B, GPIO.FALLING, callback=_make_tacho_cb(3))
    except Exception as e:
        logger.error("Tacho event detect failed: %s", e)

    # 1-Wire setup for DS18B20 temperature probes. The modprobe calls are
    # no-ops if already loaded (idempotent); still log failures for visibility.
    for mod in ("w1-gpio", "w1-therm"):
        rc = os.system(f"modprobe {mod} > /dev/null 2>&1")
        if rc != 0:
            logger.warning("modprobe %s returned %d — w1 may not be available", mod, rc)
    _discover_sensors()

    _temp_thread = threading.Thread(target=_temp_loop, name="vents-temp", daemon=True)
    _temp_thread.start()
    _auto_thread = threading.Thread(target=_auto_loop, name="vents-auto", daemon=True)
    _auto_thread.start()

    logger.info(
        "Vents GPIO: peltier=%s fan_pwm=[%d,%d] tacho=[%d,%d,%d,%d]",
        PELTIER_PINS, PIN_PWM_FAN_1, PIN_PWM_FAN_2,
        PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B, PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B,
    )


def cleanup():
    logger.info("Vents shutdown — peltiers off, fans stopped")
    _shutdown_event.set()
    if _auto_thread is not None:
        _auto_thread.join(timeout=1.0)
    if _temp_thread is not None:
        _temp_thread.join(timeout=1.0)
    try:
        for pin in PELTIER_PINS:
            GPIO.output(pin, GPIO.LOW)
    except Exception as e:
        logger.debug("Peltier cleanup output error: %s", e)
    if pwm_fan_1 is not None:
        try:
            pwm_fan_1.ChangeDutyCycle(0)
            pwm_fan_1.stop()
        except Exception as e:
            logger.debug("pwm_fan_1 cleanup error: %s", e)
    if pwm_fan_2 is not None:
        try:
            pwm_fan_2.ChangeDutyCycle(0)
            pwm_fan_2.stop()
        except Exception as e:
            logger.debug("pwm_fan_2 cleanup error: %s", e)
    for pin in (PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B, PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B):
        try:
            GPIO.remove_event_detect(pin)
        except Exception as e:
            logger.debug("remove_event_detect(%d) error: %s", pin, e)


# ── OSC handlers ──────────────────────────────────────────────────────────

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


def _handle_peltier_one(index, value):
    """Manual peltier control; switches auto → raw unless over-temperature interlock applies."""
    global mode
    want_on = bool(int(value))
    if _over_temp_interlock():
        if want_on:
            logger.info("Peltier on suppressed (over temperature interlock)")
        _set_peltier(index, False)
        return
    if mode == "auto":
        logger.info("Peltier override → switching mode to raw")
        mode = "raw"
    _set_peltier(index, want_on)


@_safe("peltier_1")
def handle_peltier_1(address, *args):
    if args:
        _handle_peltier_one(0, args[0])


@_safe("peltier_2")
def handle_peltier_2(address, *args):
    if args:
        _handle_peltier_one(1, args[0])


@_safe("peltier_3")
def handle_peltier_3(address, *args):
    if args:
        _handle_peltier_one(2, args[0])


@_safe("peltier_mask")
def handle_peltier_mask(address, *args):
    global mode
    if not args:
        return
    mask = int(args[0]) & 0b111
    if _over_temp_interlock():
        if mask != 0:
            logger.info("Peltier mask suppressed (over temperature interlock)")
        _apply_peltier_mask(0)
        return
    if mode == "auto":
        logger.info("Peltier mask override → switching mode to raw")
        mode = "raw"
    _apply_peltier_mask(mask)


@_safe("fan_1")
def handle_fan_1(address, *args):
    global mode
    if not args:
        return
    if mode == "auto":
        logger.info("Fan 1 override → switching mode to raw")
        mode = "raw"
    _set_fan(0, _clamp(float(args[0]), 0.0, 1.0))


@_safe("fan_2")
def handle_fan_2(address, *args):
    global mode
    if not args:
        return
    if mode == "auto":
        logger.info("Fan 2 override → switching mode to raw")
        mode = "raw"
    _set_fan(1, _clamp(float(args[0]), 0.0, 1.0))


@_safe("mode")
def handle_mode(address, *args):
    global mode
    if not args:
        return
    requested = str(args[0]).strip().lower()
    if requested not in ("raw", "auto"):
        raise ValueError(f"mode must be 'raw' or 'auto', got {requested!r}")
    mode = requested
    if mode == "auto":
        _set_fan(0, 0.0)
        _set_fan(1, 0.0)
    logger.info("Vents mode → %s", mode)


@_safe("target")
def handle_target(address, *args):
    global target_temp_c
    if not args:
        return
    target_temp_c = float(args[0])
    _clamp_target_vs_max()
    logger.info("Vents target temperature → %.2f °C", target_temp_c)


@_safe("max_temp")
def handle_max_temp(address, *args):
    if not args:
        return
    _set_max_temp_c(args[0])


def register_osc(dispatcher):
    dispatcher.map("/vents/peltier/1", handle_peltier_1)
    dispatcher.map("/vents/peltier/2", handle_peltier_2)
    dispatcher.map("/vents/peltier/3", handle_peltier_3)
    dispatcher.map("/vents/peltier", handle_peltier_mask)
    dispatcher.map("/vents/fan/1", handle_fan_1)
    dispatcher.map("/vents/fan/2", handle_fan_2)
    dispatcher.map("/vents/mode", handle_mode)
    dispatcher.map("/vents/target", handle_target)
    dispatcher.map("/vents/max_temp", handle_max_temp)


# ── HTTP test surface ─────────────────────────────────────────────────────

def handle_http_test(body):
    """Direct probe mirroring the OSC surface. Body:
        {command: "peltier"|"peltier_mask"|"fan"|"mode"|"target"|"max_temp",
         index?: 1|2|3 (peltier) or 1|2 (fan),
         value: ...}
    Returns current readings.
    """
    body = body or {}
    cmd = body.get("command")
    value = body.get("value")
    try:
        if cmd == "peltier":
            idx = int(body.get("index", 1)) - 1
            if idx < 0 or idx > 2:
                return {"ok": False, "error": "peltier index must be 1..3"}
            _handle_peltier_one(idx, value)
        elif cmd == "peltier_mask":
            handle_peltier_mask("/http", int(value))
        elif cmd == "fan":
            idx = int(body.get("index", 1)) - 1
            if idx not in (0, 1):
                return {"ok": False, "error": "fan index must be 1..2"}
            (handle_fan_1 if idx == 0 else handle_fan_2)("/http", float(value))
        elif cmd == "mode":
            handle_mode("/http", str(value))
        elif cmd == "target":
            handle_target("/http", float(value))
        elif cmd == "max_temp":
            handle_max_temp("/http", float(value))
        else:
            return {"ok": False, "error": f"unknown command: {cmd!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **get_status()}


# ── snapshot + describe ───────────────────────────────────────────────────

def _fan_pct_to_0_1(pct):
    return pct / 100.0


def get_status():
    """Used by both the /vents/status OSC broadcaster and HTTP /gpio/test."""
    return {
        "temp1_c": temp_c[0],
        "temp2_c": temp_c[1],
        "fan1": _fan_pct_to_0_1(fan_duty[0]),
        "fan2": _fan_pct_to_0_1(fan_duty[1]),
        "peltier_mask": _peltier_mask(),
        "peltier": list(peltier_state),
        "rpm1A": tacho_rpm[0],
        "rpm1B": tacho_rpm[1],
        "rpm2A": tacho_rpm[2],
        "rpm2B": tacho_rpm[3],
        "target_c": target_temp_c,
        "max_temp_c": max_temp_c,
        "mode": mode,
        "state": state,
        "sensors_ok": any(t is not None for t in temp_c),
    }


def get_status_osc_args():
    """OSC argument list matching the documented /vents/status contract.
    Missing temperatures are encoded as -1.0 (python-osc rejects None)."""
    s = get_status()
    return [
        float(s["temp1_c"]) if s["temp1_c"] is not None else -1.0,
        float(s["temp2_c"]) if s["temp2_c"] is not None else -1.0,
        float(s["fan1"]),
        float(s["fan2"]),
        int(s["peltier_mask"]),
        int(s["rpm1A"]),
        int(s["rpm1B"]),
        int(s["rpm2A"]),
        int(s["rpm2B"]),
        float(s["target_c"]),
        str(s["mode"]),
        str(s["state"]),
        float(s["max_temp_c"]),
    ]


def get_last_osc_time():
    return last_osc_time


def describe():
    return {
        "controller": NAME,
        "pins": {
            "peltier": list(PELTIER_PINS),
            "fan_pwm": [PIN_PWM_FAN_1, PIN_PWM_FAN_2],
            "tacho": [PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B, PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B],
        },
        "mode": mode,
        "state": state,
        "target_c": target_temp_c,
        "max_temp_c": max_temp_c,
    }
