"""Vents controller: 3 Peltier cells + 2 PWM fans + 4 tachos + 2 DS18B20 temps.

Hardware:
  - Three Peltier stacks on GPIO {26, 25, 24}, digital on/off (active HIGH).
    Each thermoelectric module has a cold face and a hot face; when ON, heat is
    pumped from one side to the other (physics of the install determines which
    face faces the conditioned volume).
  - Fan 1 — cold-side ventilation PWM on GPIO 20; fan 2 — hot-side PWM on GPIO 18.
  - Tachos on GPIO {27, 17, 23, 22} (pair A/B per fan), falling-edge ISR
    → period → RPM.
  - Two DS18B20 probes on 1-wire (`dtoverlay=w1-gpio` in config.txt). One probe
    is physically attached to the hot face, one to the cold face. The operator
    pins each probe to its role (touch-test in the admin UI); the assignment is
    persisted by the probe's 64-bit ROM id (`28-xxxxxxxxxxxx`), so it survives
    reboots and 1-Wire enumeration order changes.

Temperature control — dual setpoints:

  - **hot_target_c** + hysteresis: setpoint for the probe assigned to the hot
    face. **cold_target_c** + hysteresis: setpoint for the probe assigned to
    the cold face. Both regulate independently. OR composition rule:
    Peltiers ON whenever `t_hot < hot_target − H` OR `t_cold > cold_target + H`
    (drive gradient if either side is unhappy). OFF only when both probes are
    inside their bands. State names heating/cooling describe whether cells are
    driven, not which Peltier face is physically hot or cold. Fans are not used
    for this loop (use raw or /vents/fan/*).
  - **max_temp_c**: **safety** ceiling (persisted on the Pi). If **any
    discovered probe** (assigned or not) reads above max, state is "over_temp":
    all Peltiers off and both fans pinned to `over_temp_fan_pct` in any mode.
    Peltier "on" commands are ignored while above max (interlock).
  - **probe_unassigned**: auto refuses to run unless both `probe_hot_id` and
    `probe_cold_id` are set AND currently in the discovered probes set.
  - Cross-clamps: hot_target + H + margin < max_temp_c, and
    cold_target + H + margin ≤ hot_target. Enforced on every save.
  - **min_fan_pct**, **max_fan_pct**, **over_temp_fan_pct**: per-Pi safety
    settings, persisted on the Pi.

OSC protocol:

  Raw commands (admin → Pi on port 9000):
    /vents/peltier/1  int 0|1
    /vents/peltier/2  int 0|1
    /vents/peltier/3  int 0|1
    /vents/peltier    int mask  (bit 0 = P1, bit 1 = P2, bit 2 = P3)
    /vents/fan/1      float 0..1
    /vents/fan/2      float 0..1
    /vents/mode       string "raw" | "auto"
    /vents/target     float °C — back-compat alias for /vents/target/hot
    /vents/target/hot   float °C — hot setpoint (regulates the hot-assigned probe)
    /vents/target/cold  float °C — cold setpoint (regulates the cold-assigned probe)
    /vents/max_temp   float safety max °C (stored in ~/.config/gpio-osc/vents_prefs.json)
    /vents/probe/assign_hot   string rom_id (28-xxxxxxxxxxxx) — pin probe to hot role
    /vents/probe/assign_cold  string rom_id — pin probe to cold role
    /vents/probe/clear        string "hot"|"cold"|"both" — clear assignment(s)

  Configuration push (admin → Pi on port 9000; mirrored on HTTP /gpio/test
  via {"command": ..., "value": ...} bodies):
    /vents/config/min_fan_pct          float 0..100 — PWM floor (persisted)
    /vents/config/max_fan_pct          float 0..100 — PWM scale, applied to every
                                       fan command (persisted). Replaces the admin
                                       playback engine's old output_cap.
    /vents/config/over_temp_fan_pct    float 0..100 — fan % during over_temp (persisted)

  HTTP `snapshot` command (no-op): returns full status (incl. probes list).

  Status broadcast (Pi → admin on port 9001) every VENTS_STATUS_HZ ticks:
    /vents/status temp1, temp2, fan1_0_1, fan2_0_1, peltier_mask,
                  rpm1A, rpm1B, rpm2A, rpm2B, target_c, mode, state,
                  max_temp_c, min_fan_pct, over_temp_fan_pct, max_fan_pct,
                  temp_hot_c, temp_cold_c, hot_target_c, cold_target_c
    target_c at position 9 mirrors hot_target_c (back-compat). The dual-
    setpoint tail (positions 16-19) is forward-compat — older admins ignore.
    Missing temps (incl. temp_hot_c / temp_cold_c) are encoded as -1.0.

Auto loop branches (first match wins):
  ANY discovered probe > max_temp_c → over_temp (Peltiers off, fans → over_temp_fan_pct).
  mode != "auto"        → idle.
  either probe id null/missing → probe_unassigned (Peltiers off, fans unchanged).
  assigned probe reads None         → sensor_error (Peltiers off, fans off).
  t_hot < hot_target − H OR t_cold > cold_target + H → heating (mask 0b111).
  t_hot ≥ hot_target + H AND t_cold ≤ cold_target − H → cooling (mask 0).
  else → holding (deadband; mask unchanged).
"""

import glob
import json
import logging
import math
import os
import re
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
_PROBE_MIN_C = -55.0
_PROBE_MAX_C = 125.0

# ── state (module-level, read by OSC/HTTP handlers + status broadcaster) ──

pwm_fan_1 = None
pwm_fan_2 = None
fan_duty = [VENTS_FAN_PWM_MIN_PCT, VENTS_FAN_PWM_MIN_PCT]  # indices 0, 1 for fan 1/2
peltier_state = [0, 0, 0]

tacho_last_t = [0.0, 0.0, 0.0, 0.0]  # 1A, 1B, 2A, 2B
tacho_rpm = [0.0, 0.0, 0.0, 0.0]

# ROM-keyed discovery state (replaces _temp_files = [None, None])
# Each DS18B20 has a unique 64-bit serial; we identify probes by that ID
# (the `28-xxxxxxxxxxxx` folder name on /sys/bus/w1/devices) instead of by
# enumeration order, so probe roles survive boot/swap/hot-plug.
_probes: dict = {}        # rom_id -> /sys/.../w1_slave path
_probe_temps: dict = {}   # rom_id -> last reading °C (None on read failure)

# Back-compat 2-slot view kept for the positional /vents/status broadcast
# (temp1_c / temp2_c). Recomputed each tick from sorted(_probes.keys())[:2].
temp_c = [None, None]

# Role pinning. Persisted in vents_prefs.json. None = unassigned.
# Auto loop refuses to run unless both ids are set AND currently in _probes.
probe_hot_id = None        # rom_id of probe physically attached to the hot face
probe_cold_id = None       # rom_id of probe physically attached to the cold face

# Dual setpoints. Both regulated independently; OR composition (see _auto_loop).
hot_target_c = float(VENTS_DEFAULT_TARGET_C)
cold_target_c = float(VENTS_DEFAULT_TARGET_C)
max_temp_c = float(VENTS_DEFAULT_MAX_TEMP_C)  # over-temp threshold; persisted in _PREFS_PATH

_ROM_ID_RE = re.compile(r"^28-[0-9a-fA-F]{12}$")
# PWM floor enforced inside _set_fan whenever a non-zero duty is requested.
# Editable from admin Settings; persisted in _PREFS_PATH.
min_fan_pct = float(VENTS_FAN_PWM_MIN_PCT)
# PWM ceiling: every non-zero fan command is multiplied by max_fan_pct/100
# before the floor is applied. Replaces the playback-engine "output_cap" so
# the cap is enforced regardless of who issued the command.
max_fan_pct = 100.0
# Fan PWM forced (both fans) while any sensor exceeds max_temp_c.
# Editable from admin Settings; persisted in _PREFS_PATH.
over_temp_fan_pct = 100.0
mode = "raw"          # "raw" or "auto"
state = "idle"        # idle|heating|cooling|holding|sensor_error|probe_unassigned|over_temp

last_osc_time = 0.0
_webhooks = None

_shutdown_event = threading.Event()
_auto_thread = None
_temp_thread = None


# ── helpers ───────────────────────────────────────────────────────────────

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _clamp_setpoints():
    """Enforce the cross-clamp invariants between cold_target_c, hot_target_c,
    and max_temp_c. Always pulls values DOWN, never raises max_temp_c.

    Invariants after this returns:
      - hot_target_c  + H + margin <  max_temp_c   (hot band stays below safety)
      - cold_target_c + H + margin <= hot_target_c (cold setpoint below hot
        setpoint — otherwise the OR rule in _auto_loop is permanently triggered).
    """
    global hot_target_c, cold_target_c
    hot_ceiling = max_temp_c - VENTS_HYSTERESIS_C - _BAND_MARGIN_C
    if hot_target_c > hot_ceiling:
        logger.warning(
            "hot_target_c clamped %.2f → %.2f (max_temp_c=%.2f, H=%.2f)",
            hot_target_c, hot_ceiling, max_temp_c, VENTS_HYSTERESIS_C,
        )
        hot_target_c = hot_ceiling
    cold_ceiling = hot_target_c - VENTS_HYSTERESIS_C - _BAND_MARGIN_C
    if cold_target_c > cold_ceiling:
        logger.warning(
            "cold_target_c clamped %.2f → %.2f (hot_target_c=%.2f, H=%.2f)",
            cold_target_c, cold_ceiling, hot_target_c, VENTS_HYSTERESIS_C,
        )
        cold_target_c = cold_ceiling


_PREFS_RANGES = {
    "max_temp_c": (-55.0, 125.0),
    "min_fan_pct": (0.0, 100.0),
    "max_fan_pct": (0.0, 100.0),
    "over_temp_fan_pct": (0.0, 100.0),
    "hot_target_c": (-55.0, 125.0),
    "cold_target_c": (-55.0, 125.0),
}


def _load_prefs():
    """Load persisted vents preferences from disk (called from setup)."""
    global probe_hot_id, probe_cold_id
    try:
        data = json.loads(_PREFS_PATH.read_text())
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning("Failed to load vents prefs from %s: %s", _PREFS_PATH, e)
        return

    # One-shot migration: legacy single setpoint → both targets default to it
    # so the install behaves "single setpoint"-like until the operator splits.
    if "target_temp_c" in data and "hot_target_c" not in data:
        try:
            legacy = float(data["target_temp_c"])
            data["hot_target_c"] = legacy
            data["cold_target_c"] = legacy
            logger.info("Migrated legacy target_temp_c=%.2f → hot=cold=%.2f",
                        legacy, legacy)
        except (TypeError, ValueError):
            pass

    g = globals()
    for key, (lo, hi) in _PREFS_RANGES.items():
        if key not in data:
            continue
        try:
            g[key] = _clamp(float(data[key]), lo, hi)
        except (TypeError, ValueError):
            logger.warning("Bad %s in prefs, ignoring", key)

    for id_key in ("probe_hot_id", "probe_cold_id"):
        val = data.get(id_key)
        if val is None:
            continue
        if isinstance(val, str) and _ROM_ID_RE.match(val):
            if id_key == "probe_hot_id":
                probe_hot_id = val
            else:
                probe_cold_id = val
        else:
            logger.warning("Bad %s in prefs, ignoring: %r", id_key, val)

    _clamp_setpoints()


def _save_prefs():
    """Persist editable vents preferences for reboot."""
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PREFS_PATH.with_suffix(".json.tmp")
        payload = json.dumps({
            "max_temp_c": max_temp_c,
            "min_fan_pct": min_fan_pct,
            "max_fan_pct": max_fan_pct,
            "over_temp_fan_pct": over_temp_fan_pct,
            "hot_target_c": hot_target_c,
            "cold_target_c": cold_target_c,
            "probe_hot_id": probe_hot_id,
            "probe_cold_id": probe_cold_id,
        }, indent=2) + "\n"
        tmp.write_text(payload)
        tmp.replace(_PREFS_PATH)
    except Exception as e:
        logger.error("Failed to save vents prefs to %s: %s", _PREFS_PATH, e)


def _set_max_temp_c(value):
    """Set absolute over-temperature threshold (°C) and persist."""
    global max_temp_c
    max_temp_c = _clamp(float(value), -55.0, 125.0)
    _clamp_setpoints()
    _save_prefs()
    logger.info("Vents max temperature threshold → %.2f °C (saved)", max_temp_c)


def _set_min_fan_pct(value):
    """Set fan PWM floor (% of duty cycle) and persist."""
    global min_fan_pct
    min_fan_pct = _clamp(float(value), 0.0, 100.0)
    _save_prefs()
    logger.info("Vents min fan PWM → %.2f %% (saved)", min_fan_pct)


def _set_over_temp_fan_pct(value):
    """Set fan PWM forced while over-temperature interlock is active and persist."""
    global over_temp_fan_pct
    over_temp_fan_pct = _clamp(float(value), 0.0, 100.0)
    _save_prefs()
    logger.info("Vents over-temp fan PWM → %.2f %% (saved)", over_temp_fan_pct)


def _set_max_fan_pct(value):
    """Set fan PWM ceiling (% of duty cycle) and persist."""
    global max_fan_pct
    max_fan_pct = _clamp(float(value), 0.0, 100.0)
    _save_prefs()
    logger.info("Vents max fan PWM → %.2f %% (saved)", max_fan_pct)


def _set_peltier(index, on):
    """index is 0..2 (pin 26/25/24)."""
    pin = PELTIER_PINS[index]
    GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
    peltier_state[index] = 1 if on else 0


def _set_fan(index, duty_0_1):
    """index is 0 (fan 1) or 1 (fan 2). duty_0_1 in [0, 1].

    Pipeline: clamp to [0, 100] → scale by max_fan_pct (the device-side cap
    that replaced the playback engine's output_cap) → raise to min_fan_pct
    floor. The floor is unconditional: output never drops below min_fan_pct.
    """
    raw_pct = _clamp(float(duty_0_1) * 100.0, 0.0, VENTS_FAN_PWM_MAX_PCT)
    duty_pct = max(raw_pct * (max_fan_pct / 100.0), min_fan_pct)
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
    """Scan /sys/bus/w1/devices for 28-* DS18B20 probes. Build _probes keyed
    by ROM id (the bare folder name like '28-3c01b556a8b9'). Idempotent —
    called from setup() and again on a slow rescan tick from _temp_loop so
    unplug/replug is picked up without restart."""
    global _probes
    new_map = {}
    try:
        for folder in sorted(glob.glob("/sys/bus/w1/devices/28*")):
            rom_id = os.path.basename(folder)
            new_map[rom_id] = os.path.join(folder, "w1_slave")
    except Exception as e:
        logger.warning("Temp sensor discovery failed: %s", e)
        return
    if set(new_map) != set(_probes):
        if new_map:
            logger.info("Probes discovered: %s", list(new_map))
        else:
            logger.warning("No DS18B20 sensors found. Check dtoverlay=w1-gpio in config.txt.")
    _probes = new_map
    # Drop temps for probes that disappeared so stale values don't trip safety.
    for stale in set(_probe_temps) - set(_probes):
        _probe_temps.pop(stale, None)


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


_RESCAN_PERIOD_S = 30.0


def _temp_loop():
    """Poll every discovered probe at VENTS_TEMP_POLL_HZ. Periodically rescan
    the 1-Wire bus so a probe wired in after boot becomes visible without a
    restart. Refresh the back-compat temp_c view from sorted ROM ids."""
    period = 1.0 / max(1, VENTS_TEMP_POLL_HZ)
    last_rescan = 0.0
    while not _shutdown_event.is_set():
        now = time.time()
        if now - last_rescan > _RESCAN_PERIOD_S:
            _discover_sensors()
            last_rescan = now
        for rom_id, path in list(_probes.items()):
            _probe_temps[rom_id] = _read_ds18b20(path)
        ordered = sorted(_probes.keys())
        for i in range(2):
            temp_c[i] = _probe_temps.get(ordered[i]) if i < len(ordered) else None
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

def _over_temp_interlock():
    """True when ANY discovered probe (assigned or not) reads above max_temp_c.
    Used by manual peltier handlers as a hard interlock that ignores `on`
    requests, and by the auto loop's safety branch."""
    return any(t is not None and t > max_temp_c for t in _probe_temps.values())


def _probe_safety_fault():
    """Fail-safe probe validation for safety lock."""
    if not _probes:
        return True
    for rom_id in _probes.keys():
        t = _probe_temps.get(rom_id)
        if t is None:
            return True
        try:
            temp = float(t)
        except (TypeError, ValueError):
            return True
        if not math.isfinite(temp):
            return True
        if temp < _PROBE_MIN_C or temp > _PROBE_MAX_C:
            return True
    return False


def _safety_lock_state():
    """Return active safety lock state name, or None when unlocked."""
    if _probe_safety_fault():
        return "sensor_error"
    if _over_temp_interlock():
        return "over_temp"
    return None


def _auto_loop():
    """Dual-setpoint bang-bang regulator with role-pinned probes (OR rule).

    Per-tick branches, first match wins:

      1. over_temp                 → ANY probe (incl. unassigned) > max_temp_c.
                                     Peltiers off, both fans pinned to
                                     over_temp_fan_pct. Enforced in raw and auto.
      2. mode != "auto"            → state=idle, return.
      3. probe_unassigned          → either role's id is null OR not currently
                                     in _probes. Peltiers off, fans off.
      4. sensor_error              → an assigned probe currently reads None.
                                     Peltiers off, fans off.
      5. heating (need_on, OR)     → t_hot < hot_target_c − H
                                     OR t_cold > cold_target_c + H.
                                     Peltiers all on (mask 0b111).
      6. cooling (need_off, AND)   → t_hot ≥ hot_target_c + H
                                     AND t_cold ≤ cold_target_c − H.
                                     Peltiers all off.
      7. holding                   → deadband — leave Peltier mask unchanged.
                                     Fans not touched in any heating/cooling/
                                     holding branch (auto doesn't drive fans).
    """
    global state
    period = 1.0 / max(1, VENTS_AUTO_LOOP_HZ)
    H = VENTS_HYSTERESIS_C
    while not _shutdown_event.is_set():
        # Safety lock is always enforced, regardless of raw/auto mode.
        lock_state = _safety_lock_state()
        if lock_state is not None:
            state = lock_state
            _apply_peltier_mask(0)
            fallback_0_1 = over_temp_fan_pct / 100.0
            _set_fan(0, fallback_0_1)
            _set_fan(1, fallback_0_1)
            _tacho_decay_tick()
            _shutdown_event.wait(period)
            continue

        if mode != "auto":
            state = "idle"
            _tacho_decay_tick()
            _shutdown_event.wait(period)
            continue

        hot_present = probe_hot_id is not None and probe_hot_id in _probes
        cold_present = probe_cold_id is not None and probe_cold_id in _probes
        if not hot_present or not cold_present:
            if state != "probe_unassigned":
                logger.warning(
                    "Auto blocked: hot=%s cold=%s discovered=%s",
                    probe_hot_id, probe_cold_id, list(_probes),
                )
            state = "probe_unassigned"
            _apply_peltier_mask(0)
            _set_fan(0, 0.0)
            _set_fan(1, 0.0)
            _tacho_decay_tick()
            _shutdown_event.wait(period)
            continue

        t_hot = _probe_temps.get(probe_hot_id)
        t_cold = _probe_temps.get(probe_cold_id)
        if t_hot is None or t_cold is None:
            if state != "sensor_error":
                logger.warning(
                    "Auto: assigned probe read failed (hot=%s cold=%s)",
                    t_hot, t_cold,
                )
            state = "sensor_error"
            _apply_peltier_mask(0)
            fallback_0_1 = over_temp_fan_pct / 100.0
            _set_fan(0, fallback_0_1)
            _set_fan(1, fallback_0_1)
            _tacho_decay_tick()
            _shutdown_event.wait(period)
            continue

        # OR composition — ON if either side wants more gradient.
        need_on = (t_hot < hot_target_c - H) or (t_cold > cold_target_c + H)
        need_off = (t_hot >= hot_target_c + H) and (t_cold <= cold_target_c - H)
        if need_on:
            state = "heating"        # name preserved for admin enum compat
            _apply_peltier_mask(0b111)
        elif need_off:
            state = "cooling"
            _apply_peltier_mask(0)
        else:
            state = "holding"        # deadband — preserve previous mask
        _tacho_decay_tick()
        _shutdown_event.wait(period)


# ── interface ─────────────────────────────────────────────────────────────

def setup(webhooks):
    global _webhooks, pwm_fan_1, pwm_fan_2, _auto_thread, _temp_thread
    _webhooks = webhooks

    _shutdown_event.clear()
    _load_prefs()
    _clamp_setpoints()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Pass initial= so rpi-lgpio (Pi 5) doesn't try to read the pin
    # before claiming it — that fails with 'GPIO not allocated' on a
    # crash-restart where the previous process didn't run cleanup.
    for pin in PELTIER_PINS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    GPIO.setup(PIN_PWM_FAN_1, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_PWM_FAN_2, GPIO.OUT, initial=GPIO.LOW)
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
    if _safety_lock_state() is not None:
        if want_on:
            logger.info("Peltier on suppressed (safety lock active)")
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
    if _safety_lock_state() is not None:
        if mask != 0:
            logger.info("Peltier mask suppressed (safety lock active)")
        _apply_peltier_mask(0)
        return
    if mode == "auto":
        logger.info("Peltier mask override → switching mode to raw")
        mode = "raw"
    _apply_peltier_mask(mask)


@_safe("fan_1")
def handle_fan_1(address, *args):
    if not args:
        return
    if _safety_lock_state() is not None:
        logger.info("Fan 1 override suppressed (safety lock active)")
        _set_fan(0, over_temp_fan_pct / 100.0)
        return
    _set_fan(0, _clamp(float(args[0]), 0.0, 1.0))


@_safe("fan_2")
def handle_fan_2(address, *args):
    if not args:
        return
    if _safety_lock_state() is not None:
        logger.info("Fan 2 override suppressed (safety lock active)")
        _set_fan(1, over_temp_fan_pct / 100.0)
        return
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
    logger.info("Vents mode → %s", mode)


@_safe("target_hot")
def handle_target_hot(address, *args):
    """Set the hot setpoint (regulates the probe assigned to the hot face).
    Persisted. Cross-clamped against max_temp_c, then forces cold_target_c
    down if it would otherwise breach the cold ≤ hot − H − margin invariant."""
    global hot_target_c
    if not args:
        return
    hot_target_c = float(args[0])
    _clamp_setpoints()
    _save_prefs()
    logger.info("Vents hot target → %.2f °C (cold=%.2f, saved)",
                hot_target_c, cold_target_c)


@_safe("target_cold")
def handle_target_cold(address, *args):
    """Set the cold setpoint (regulates the probe assigned to the cold face).
    Persisted. Clamped to ≤ hot_target_c − H − margin so the OR rule isn't
    permanently triggered."""
    global cold_target_c
    if not args:
        return
    cold_target_c = float(args[0])
    _clamp_setpoints()
    _save_prefs()
    logger.info("Vents cold target → %.2f °C (hot=%.2f, saved)",
                cold_target_c, hot_target_c)


@_safe("target")
def handle_target(address, *args):
    """Back-compat alias — legacy /vents/target routes to the hot setpoint."""
    handle_target_hot(address, *args)


def _validate_rom_id(value):
    """Returns the trimmed ROM id if it matches /^28-[0-9a-fA-F]{12}$/, else None."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if _ROM_ID_RE.match(v) else None


def _assign_probe(role, value):
    """Assign a ROM id to `role` ("hot" or "cold"). Persists. Rejects an
    id already assigned to the other role. Persists ids whose probe isn't
    currently on the bus too — operator may be configuring before wiring."""
    global probe_hot_id, probe_cold_id
    rom_id = _validate_rom_id(value)
    if rom_id is None:
        raise ValueError(f"invalid ROM id: {value!r} (expected 28-xxxxxxxxxxxx)")
    other = probe_cold_id if role == "hot" else probe_hot_id
    if rom_id == other:
        other_label = "cold" if role == "hot" else "hot"
        raise ValueError(f"{rom_id} is already assigned as {other_label} probe")
    if role == "hot":
        probe_hot_id = rom_id
    else:
        probe_cold_id = rom_id
    _save_prefs()
    if rom_id not in _probes:
        logger.warning("%s probe assigned to %s but not currently discovered",
                       role.capitalize(), rom_id)
    else:
        logger.info("%s probe → %s (saved)", role.capitalize(), rom_id)


@_safe("probe_assign_hot")
def handle_probe_assign_hot(address, *args):
    if args:
        _assign_probe("hot", args[0])


@_safe("probe_assign_cold")
def handle_probe_assign_cold(address, *args):
    if args:
        _assign_probe("cold", args[0])


@_safe("probe_clear")
def handle_probe_clear(address, *args):
    """Clear one or both probe assignments. Argument is 'hot', 'cold', or 'both'."""
    global probe_hot_id, probe_cold_id
    if not args:
        return
    which = str(args[0]).strip().lower()
    if which not in ("hot", "cold", "both"):
        raise ValueError(f"probe_clear must be 'hot'|'cold'|'both', got {which!r}")
    if which in ("hot", "both"):
        probe_hot_id = None
    if which in ("cold", "both"):
        probe_cold_id = None
    _save_prefs()
    logger.info("Probe assignment cleared (%s)", which)


@_safe("max_temp")
def handle_max_temp(address, *args):
    if not args:
        return
    _set_max_temp_c(args[0])


@_safe("min_fan_pct")
def handle_min_fan_pct(address, *args):
    if not args:
        return
    _set_min_fan_pct(args[0])


@_safe("over_temp_fan_pct")
def handle_over_temp_fan_pct(address, *args):
    if not args:
        return
    _set_over_temp_fan_pct(args[0])


@_safe("max_fan_pct")
def handle_max_fan_pct(address, *args):
    if not args:
        return
    _set_max_fan_pct(args[0])


def register_osc(dispatcher):
    dispatcher.map("/vents/peltier/1", handle_peltier_1)
    dispatcher.map("/vents/peltier/2", handle_peltier_2)
    dispatcher.map("/vents/peltier/3", handle_peltier_3)
    dispatcher.map("/vents/peltier", handle_peltier_mask)
    dispatcher.map("/vents/fan/1", handle_fan_1)
    dispatcher.map("/vents/fan/2", handle_fan_2)
    dispatcher.map("/vents/mode", handle_mode)
    dispatcher.map("/vents/target", handle_target)              # alias → hot
    dispatcher.map("/vents/target/hot", handle_target_hot)
    dispatcher.map("/vents/target/cold", handle_target_cold)
    dispatcher.map("/vents/max_temp", handle_max_temp)
    dispatcher.map("/vents/probe/assign_hot", handle_probe_assign_hot)
    dispatcher.map("/vents/probe/assign_cold", handle_probe_assign_cold)
    dispatcher.map("/vents/probe/clear", handle_probe_clear)
    dispatcher.map("/vents/config/min_fan_pct", handle_min_fan_pct)
    dispatcher.map("/vents/config/max_fan_pct", handle_max_fan_pct)
    dispatcher.map("/vents/config/over_temp_fan_pct", handle_over_temp_fan_pct)


# ── HTTP test surface ─────────────────────────────────────────────────────

def handle_http_test(body):
    """Direct probe mirroring the OSC surface. Body:
        {command: "peltier"|"peltier_mask"|"fan"|"mode"
                 |"target"|"target_hot"|"target_cold"|"max_temp"
                 |"probe_assign_hot"|"probe_assign_cold"|"probe_clear"
                 |"snapshot",
         index?: 1|2|3 (peltier) or 1|2 (fan),
         value: ...}

    `snapshot` is a no-op used by the admin to fetch the full status
    (including the discovered probes list). Returns current readings.
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
        elif cmd == "target_hot":
            handle_target_hot("/http", float(value))
        elif cmd == "target_cold":
            handle_target_cold("/http", float(value))
        elif cmd == "max_temp":
            handle_max_temp("/http", float(value))
        elif cmd == "probe_assign_hot":
            handle_probe_assign_hot("/http", str(value))
        elif cmd == "probe_assign_cold":
            handle_probe_assign_cold("/http", str(value))
        elif cmd == "probe_clear":
            handle_probe_clear("/http", str(value))
        elif cmd == "min_fan_pct":
            handle_min_fan_pct("/http", float(value))
        elif cmd == "max_fan_pct":
            handle_max_fan_pct("/http", float(value))
        elif cmd == "over_temp_fan_pct":
            handle_over_temp_fan_pct("/http", float(value))
        elif cmd == "snapshot":
            pass  # no-op: returns get_status() below
        else:
            return {"ok": False, "error": f"unknown command: {cmd!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **get_status()}


# ── snapshot + describe ───────────────────────────────────────────────────

def _fan_pct_to_0_1(pct):
    return pct / 100.0


def get_status():
    """Used by the /vents/status OSC broadcaster and HTTP /gpio/test.

    `temp1_c` / `temp2_c` are the legacy raw probe-order view (kept for
    back-compat with old admin builds). The role-based view (`temp_hot_c`,
    `temp_cold_c`, `probe_hot_id`, `probe_cold_id`) is the canonical one.
    `probes` is the full discovery list, used by the admin's assignment UI.
    """
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
        "target_c": hot_target_c,                # back-compat alias for hot
        "hot_target_c": hot_target_c,
        "cold_target_c": cold_target_c,
        "temp_hot_c": _probe_temps.get(probe_hot_id) if probe_hot_id else None,
        "temp_cold_c": _probe_temps.get(probe_cold_id) if probe_cold_id else None,
        "probe_hot_id": probe_hot_id,
        "probe_cold_id": probe_cold_id,
        "probes": [
            {"id": rid, "temp_c": _probe_temps.get(rid)}
            for rid in sorted(_probes.keys())
        ],
        "max_temp_c": max_temp_c,
        "min_fan_pct": min_fan_pct,
        "max_fan_pct": max_fan_pct,
        "over_temp_fan_pct": over_temp_fan_pct,
        "mode": mode,
        "state": state,
        "sensors_ok": any(t is not None for t in temp_c),
    }


def get_status_osc_args():
    """OSC argument list matching the documented /vents/status contract.
    Missing temperatures are encoded as -1.0 (python-osc rejects None).
    Backend `_handle_vents_status` parses arg 13 onward optionally so older
    firmware (12 args, no max_temp_c) and pre-min-fan (13 args) both decode.

    Positions 16-19 are the dual-setpoint tail (temp_hot_c, temp_cold_c,
    hot_target_c, cold_target_c) — admin builds older than this firmware
    simply stop reading at position 15."""
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
        float(s["min_fan_pct"]),
        float(s["over_temp_fan_pct"]),
        float(s["max_fan_pct"]),
        float(s["temp_hot_c"]) if s["temp_hot_c"] is not None else -1.0,
        float(s["temp_cold_c"]) if s["temp_cold_c"] is not None else -1.0,
        float(s["hot_target_c"]),
        float(s["cold_target_c"]),
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
        "target_c": hot_target_c,
        "hot_target_c": hot_target_c,
        "cold_target_c": cold_target_c,
        "max_temp_c": max_temp_c,
        "probe_hot_id": probe_hot_id,
        "probe_cold_id": probe_cold_id,
    }
