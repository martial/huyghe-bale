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

Temperature control — last-target-wins regulation:

  - **hot_target_c** + hysteresis: setpoint for the probe assigned to the hot
    face. **cold_target_c** + hysteresis: setpoint for the probe assigned to
    the cold face. **active_target** ∈ {"hot","cold"} selects which side
    currently regulates; the other value is preserved on disk but inactive.
    Writing /vents/target/{hot,cold} flips active to that side; the dedicated
    /vents/target/active flips without changing values. Default is "hot".
  - The active side runs simple bang-bang on its own probe:
      active=hot:  ON if t_hot < hot_target − H,  OFF if t_hot ≥ hot_target + H
      active=cold: ON if t_cold > cold_target + H, OFF if t_cold ≤ cold_target − H
    The single `heating` state means the regulator is engaged; the peltier
    mask differentiates cells driven on from cells driven off. Physical
    heat-flow direction depends on which face is exposed to the conditioned
    volume. Fans are not used for this loop (use raw or /vents/fan/*).
  - **max_temp_c**: **safety** ceiling (persisted on the Pi). If **any
    discovered probe** (assigned or not) reads above max, state is "over_temp":
    all Peltiers off and both fans pinned to `over_temp_fan_pct` in any mode.
    Peltier "on" commands are ignored while above max (interlock).
  - **probe_unassigned**: auto refuses to run unless both `probe_hot_id` and
    `probe_cold_id` are set AND currently in the discovered probes set
    (uniform safety — even though only one side regulates).
  - Clamps: hot_target + H + margin < max_temp_c (kept), and both setpoints
    are floored at _TARGET_MIN_C (15 °C, operator-facing). Enforced on every
    save and at load time. The cold-vs-hot invariant is no longer needed.
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
    /vents/target/hot   float °C — hot setpoint (also flips active=hot)
    /vents/target/cold  float °C — cold setpoint (also flips active=cold)
    /vents/target/active string "hot"|"cold" — flip active side, no value change
    /vents/max_temp   float safety max °C (stored in ~/.config/gpio-osc/vents_prefs.json)
    /vents/unique_peltier  int 0|1 — drive one cell at a time in auto (persisted)
    /vents/peltier_rest_s  int seconds — per-cell minimum-OFF cooldown (0..3600, persisted)
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
                  temp_hot_c, temp_cold_c, hot_target_c, cold_target_c,
                  active_target,
                  unique_peltier, peltier_rest_s, active_peltier_index
    target_c at position 9 mirrors hot_target_c (back-compat). Position 20
    (active_target) is forward-compat — older admins stop reading at 19 and
    fall back to displaying both setpoints as if both were active. Positions
    21/22/23 carry unique_peltier (0|1), peltier_rest_s (int s) and the
    currently-active cell index in unique mode (0..2; -1 when none). Older
    admins simply stop reading at 20.
    Missing temps (incl. temp_hot_c / temp_cold_c) are encoded as -1.0.
    Per-cell rest-remaining (peltier_rest_remaining[3]) is HTTP-snapshot only.

Auto loop branches (first match wins):
  ANY discovered probe > max_temp_c → over_temp (Peltiers off, fans → over_temp_fan_pct).
  mode != "auto"        → idle.
  either probe id null/missing → probe_unassigned (Peltiers off, fans off).
  assigned probe reads None         → sensor_error (Peltiers off, fans pinned).
  active=hot:  t_hot < hot_target − H   → heating (drive on; mask 0b111 or one cell in unique mode).
               t_hot ≥ hot_target + H   → heating (drive off; mask 0).
  active=cold: t_cold > cold_target + H → heating (drive on).
               t_cold ≤ cold_target − H → heating (drive off).
  else → holding (deadband; mask unchanged).

When `unique_peltier` is True and the branch decides to drive on, only one cell
is energized — the eligible cell whose last on→off transition is oldest (ties
broken by lowest index). A cell is eligible when `now − last_off ≥
peltier_rest_s` (or it has never run). If no cell is eligible the state is
"rest_wait" and the mask stays 0 until one becomes eligible. Cells are timed
independently; the rest threshold is shared. Manual /vents/peltier/* writes in
raw mode bypass the rest constraint but still stamp last_off on on→off so the
auto loop honors the timer afterward.
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
    VENTS_PELTIER_REST_DEFAULT_S, VENTS_PELTIER_REST_MAX_S,
)

logger = logging.getLogger(__name__)

NAME = "vents"
STATUS_BROADCAST_ADDRESS = "/vents/status"
STATUS_BROADCAST_HZ = VENTS_STATUS_HZ

PELTIER_PINS = (PIN_PELTIER_1, PIN_PELTIER_2, PIN_PELTIER_3)

_PREFS_PATH = Path(os.path.expanduser("~/.config/gpio-osc/vents_prefs.json"))
# Keep max_temp_c strictly above the upper regulation edge (target + H).
_BAND_MARGIN_C = 0.05
# Operator-facing floor for both setpoints. Pi-side clamp is authoritative;
# the admin slider mirrors this minimum but cannot lower it.
_TARGET_MIN_C = 15.0
_PROBE_MIN_C = -55.0
_PROBE_MAX_C = 125.0
_VALID_ACTIVE_TARGETS = ("hot", "cold")

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

# Dual setpoints, but only the *active* one regulates at any time. The other
# value is preserved on disk so the operator can flip back without re-typing.
# `active_target` is set by the most recent /vents/target/{hot,cold} write, or
# explicitly via /vents/target/active.
hot_target_c = float(VENTS_DEFAULT_TARGET_C)
cold_target_c = float(VENTS_DEFAULT_TARGET_C)
active_target = "hot"  # "hot" | "cold". Persisted. Last setpoint write wins.
max_temp_c = float(VENTS_DEFAULT_MAX_TEMP_C)  # over-temp threshold; persisted in _PREFS_PATH

# "Unique peltier" sub-mode of auto. When True the auto loop drives only one
# cell at a time; each cell tracks its own minimum-OFF cooldown against the
# shared `peltier_rest_s` threshold. Timers (peltier_last_off_monotonic[3])
# are in-memory only — after a reboot every cell is "never run" and eligible
# immediately. Persisted: unique_peltier (bool), peltier_rest_s (int seconds).
unique_peltier = False
peltier_rest_s = VENTS_PELTIER_REST_DEFAULT_S          # integer seconds
peltier_last_off_monotonic = [0.0, 0.0, 0.0]  # time.monotonic() of last on→off
active_peltier_index = None  # Optional[int] — currently driven cell in unique mode

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
state = "idle"        # idle|heating|holding|sensor_error|probe_unassigned|over_temp|rest_wait

last_osc_time = 0.0
_webhooks = None

_shutdown_event = threading.Event()
_auto_thread = None
_temp_thread = None


# ── helpers ───────────────────────────────────────────────────────────────

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _clamp_setpoints():
    """Enforce setpoint bounds. Always pulls values toward valid range; never
    raises max_temp_c.

    Invariants after this returns:
      - hot_target_c  + H + margin <  max_temp_c   (hot band stays below safety)
      - hot_target_c  >= _TARGET_MIN_C             (operator floor; default 15 °C)
      - cold_target_c >= _TARGET_MIN_C

    There is no longer a hot-vs-cold invariant: with "last target wins"
    regulation only one side is active at a time, so independent values are fine.
    """
    global hot_target_c, cold_target_c
    hot_ceiling = max_temp_c - VENTS_HYSTERESIS_C - _BAND_MARGIN_C
    if hot_target_c > hot_ceiling:
        logger.warning(
            "hot_target_c clamped %.2f → %.2f (max_temp_c=%.2f, H=%.2f)",
            hot_target_c, hot_ceiling, max_temp_c, VENTS_HYSTERESIS_C,
        )
        hot_target_c = hot_ceiling
    if hot_target_c < _TARGET_MIN_C:
        logger.warning(
            "hot_target_c clamped %.2f → %.2f (operator floor)",
            hot_target_c, _TARGET_MIN_C,
        )
        hot_target_c = _TARGET_MIN_C
    if cold_target_c < _TARGET_MIN_C:
        logger.warning(
            "cold_target_c clamped %.2f → %.2f (operator floor)",
            cold_target_c, _TARGET_MIN_C,
        )
        cold_target_c = _TARGET_MIN_C


_PREFS_RANGES = {
    "max_temp_c": (-55.0, 125.0),
    "min_fan_pct": (0.0, 100.0),
    "max_fan_pct": (0.0, 100.0),
    "over_temp_fan_pct": (0.0, 100.0),
    "hot_target_c": (_TARGET_MIN_C, 125.0),
    "cold_target_c": (_TARGET_MIN_C, 125.0),
}


def _load_prefs():
    """Load persisted vents preferences from disk (called from setup)."""
    global probe_hot_id, probe_cold_id, active_target, unique_peltier, peltier_rest_s
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

    saved_active = data.get("active_target")
    if isinstance(saved_active, str) and saved_active in _VALID_ACTIVE_TARGETS:
        active_target = saved_active
    elif saved_active is not None:
        logger.warning("Bad active_target in prefs, defaulting to 'hot': %r", saved_active)

    if "unique_peltier" in data:
        try:
            unique_peltier = bool(int(data["unique_peltier"]))
        except (TypeError, ValueError):
            logger.warning("Bad unique_peltier in prefs, ignoring: %r", data["unique_peltier"])

    if "peltier_rest_s" in data:
        try:
            peltier_rest_s = _clamp(int(data["peltier_rest_s"]), 0, VENTS_PELTIER_REST_MAX_S)
        except (TypeError, ValueError):
            logger.warning("Bad peltier_rest_s in prefs, ignoring: %r", data["peltier_rest_s"])

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
            "active_target": active_target,
            "probe_hot_id": probe_hot_id,
            "probe_cold_id": probe_cold_id,
            "unique_peltier": int(unique_peltier),
            "peltier_rest_s": peltier_rest_s,
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
    """index is 0..2 (pin 26/25/24).

    Every on→off transition stamps `peltier_last_off_monotonic[index]` so the
    unique-peltier rest timer reflects reality across all paths — auto, raw,
    mask handler, safety lock and cleanup all funnel through here.
    """
    pin = PELTIER_PINS[index]
    was_on = peltier_state[index]
    GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
    peltier_state[index] = 1 if on else 0
    if was_on and not on:
        peltier_last_off_monotonic[index] = time.monotonic()


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


def _peltier_rest_remaining_s():
    """[r0, r1, r2] — seconds until each cell is eligible to be re-driven in
    unique-peltier mode. 0.0 means eligible now (incl. never-run cells, which
    have last_off == 0.0)."""
    now = time.monotonic()
    out = []
    for last in peltier_last_off_monotonic:
        if last == 0.0:
            out.append(0.0)
        else:
            out.append(_clamp(peltier_rest_s - (now - last), 0.0, peltier_rest_s))
    return out


def _pick_unique_peltier_index():
    """Choose which cell to drive in unique mode.

    Returns:
      - `active_peltier_index` if it's currently set AND that cell is on
        (keep driving it across ticks);
      - else the eligible cell whose `last_off` is oldest (longest rested);
        ties broken by lowest index. Never-run cells (last_off == 0.0) sort
        before any with a non-zero stamp, which is the desired tie-break on
        fresh boot.
      - None if no cell is eligible (every cell is still resting).

    A cell is eligible when `now − last_off ≥ peltier_rest_s` OR `last_off
    == 0.0` (the never-run sentinel).
    """
    if active_peltier_index is not None and peltier_state[active_peltier_index]:
        return active_peltier_index
    now = time.monotonic()
    eligible = []
    for i in range(3):
        last = peltier_last_off_monotonic[i]
        if last == 0.0 or (now - last) >= peltier_rest_s:
            # Sort key: (last_off, index). 0.0 sorts first → never-run preferred.
            eligible.append((last, i))
    if not eligible:
        return None
    eligible.sort()
    return eligible[0][1]


def _auto_loop():
    """Single-active-side bang-bang regulator with role-pinned probes.

    With one binary actuator (Peltier on/off) the controller can only honor
    one regulation target at a time. `active_target` (set by the most recent
    setpoint write) selects which side currently regulates; the other is
    persisted but inactive.

    Per-tick branches, first match wins:

      1. over_temp                 → ANY probe (incl. unassigned) > max_temp_c.
                                     Peltiers off, both fans pinned to
                                     over_temp_fan_pct. Enforced in raw and auto.
      2. mode != "auto"            → state=idle, return.
      3. probe_unassigned          → either role's id is null OR not currently
                                     in _probes. Peltiers off, fans off. Both
                                     probes still required for uniform safety.
      4. sensor_error              → an assigned probe currently reads None.
                                     Peltiers off, fans pinned to safety fallback.
      5. heating (need_on / need_off) →
                                     active=hot:  t_hot < hot_target_c − H   (drive on)
                                                  t_hot ≥ hot_target_c + H   (drive off)
                                     active=cold: t_cold > cold_target_c + H (drive on)
                                                  t_cold ≤ cold_target_c − H (drive off)
                                     Standard mode: mask 0b111 when on, 0 when off.
                                     Unique mode: single-bit mask when on, 0 when off;
                                       if no cell is eligible while on is requested →
                                       state="rest_wait", mask 0.
                                     _set_peltier stamps last_off for any cell that
                                     transitions on→off.
      6. holding                   → deadband — leave Peltier mask unchanged.
                                     Fans not touched in heating/holding (auto
                                     doesn't drive fans).

    Mid-flight collapse: if `unique_peltier` flips True while more than one
    cell is currently driven (e.g. the previous tick used the standard mask
    0b111, or the operator was driving multiple cells in raw before flipping
    to auto+unique), the next tick collapses to the lowest-index cell that
    is on; the others go off (and stamp their last_off).
    """
    global state, active_peltier_index
    period = 1.0 / max(1, VENTS_AUTO_LOOP_HZ)
    H = VENTS_HYSTERESIS_C
    while not _shutdown_event.is_set():
        # Safety lock is always enforced, regardless of raw/auto mode.
        lock_state = _safety_lock_state()
        if lock_state is not None:
            state = lock_state
            _apply_peltier_mask(0)
            active_peltier_index = None
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

        # Mid-flight collapse: a multi-cell mask is illegal in unique mode.
        # Keep the lowest-index cell currently on; the others go off and
        # _set_peltier stamps their last_off.
        if unique_peltier and bin(_peltier_mask()).count("1") > 1:
            keep = next((i for i in range(3) if peltier_state[i]), None)
            for i in range(3):
                if i != keep:
                    _set_peltier(i, False)
            active_peltier_index = keep

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
            active_peltier_index = None
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
            active_peltier_index = None
            fallback_0_1 = over_temp_fan_pct / 100.0
            _set_fan(0, fallback_0_1)
            _set_fan(1, fallback_0_1)
            _tacho_decay_tick()
            _shutdown_event.wait(period)
            continue

        # Single-active-side bang-bang. Only the active probe drives the mask;
        # the other side's reading is observed for safety only (over_temp /
        # sensor_error branches above already covered it).
        if active_target == "cold":
            need_on = t_cold > cold_target_c + H   # too warm → pump heat away
            need_off = t_cold <= cold_target_c - H
        else:  # "hot"
            need_on = t_hot < hot_target_c - H     # too cool → pump heat in
            need_off = t_hot >= hot_target_c + H
        if need_on:
            if unique_peltier:
                idx = _pick_unique_peltier_index()
                if idx is None:
                    state = "rest_wait"
                    _apply_peltier_mask(0)
                    active_peltier_index = None
                else:
                    state = "heating"
                    _apply_peltier_mask(1 << idx)
                    active_peltier_index = idx
            else:
                state = "heating"            # name preserved for admin enum compat
                _apply_peltier_mask(0b111)
                active_peltier_index = None
        elif need_off:
            state = "heating"
            _apply_peltier_mask(0)           # _set_peltier stamps last_off
            active_peltier_index = None
        else:
            state = "holding"                # deadband — preserve previous mask
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
    """Set the hot setpoint and make hot the active regulation target.
    Persisted. Clamped against max_temp_c (upper) and the 15 °C operator floor."""
    global hot_target_c, active_target
    if not args:
        return
    hot_target_c = float(args[0])
    active_target = "hot"
    _clamp_setpoints()
    _save_prefs()
    logger.info("Vents hot target → %.2f °C (active=hot, saved)", hot_target_c)


@_safe("target_cold")
def handle_target_cold(address, *args):
    """Set the cold setpoint and make cold the active regulation target.
    Persisted. Clamped against the 15 °C operator floor."""
    global cold_target_c, active_target
    if not args:
        return
    cold_target_c = float(args[0])
    active_target = "cold"
    _clamp_setpoints()
    _save_prefs()
    logger.info("Vents cold target → %.2f °C (active=cold, saved)", cold_target_c)


@_safe("target_active")
def handle_target_active(address, *args):
    """Flip the active regulation side without changing either stored value.
    Used by the admin to re-activate a greyed-out setpoint with one click."""
    global active_target
    if not args:
        return
    requested = str(args[0]).strip().lower()
    if requested not in _VALID_ACTIVE_TARGETS:
        raise ValueError(f"active_target must be 'hot' or 'cold', got {requested!r}")
    active_target = requested
    _save_prefs()
    logger.info("Vents active target → %s (saved)", active_target)


@_safe("target")
def handle_target(address, *args):
    """Back-compat alias — legacy /vents/target routes to the hot setpoint
    and (as a side effect) makes hot the active target."""
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


@_safe("unique_peltier")
def handle_unique_peltier(address, *args):
    """Toggle the 'one cell at a time' sub-mode of auto. Persisted.
    Does not by itself reshape the current peltier mask — the next /auto tick
    collapses any multi-cell drive when this flag is True."""
    global unique_peltier
    if not args:
        return
    unique_peltier = bool(int(args[0]))
    _save_prefs()
    logger.info("Vents unique_peltier → %s (saved)", unique_peltier)


@_safe("peltier_rest_s")
def handle_peltier_rest_s(address, *args):
    """Set the per-cell minimum-OFF cooldown (seconds) used by unique-peltier
    auto mode. Shared threshold; timers are tracked per cell. Clamped to
    [0, VENTS_PELTIER_REST_MAX_S]. Persisted."""
    global peltier_rest_s
    if not args:
        return
    peltier_rest_s = _clamp(int(args[0]), 0, VENTS_PELTIER_REST_MAX_S)
    _save_prefs()
    logger.info("Vents peltier_rest_s → %d s (saved)", peltier_rest_s)


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
    dispatcher.map("/vents/target/active", handle_target_active)
    dispatcher.map("/vents/max_temp", handle_max_temp)
    dispatcher.map("/vents/probe/assign_hot", handle_probe_assign_hot)
    dispatcher.map("/vents/probe/assign_cold", handle_probe_assign_cold)
    dispatcher.map("/vents/probe/clear", handle_probe_clear)
    dispatcher.map("/vents/config/min_fan_pct", handle_min_fan_pct)
    dispatcher.map("/vents/config/max_fan_pct", handle_max_fan_pct)
    dispatcher.map("/vents/config/over_temp_fan_pct", handle_over_temp_fan_pct)
    dispatcher.map("/vents/unique_peltier", handle_unique_peltier)
    dispatcher.map("/vents/peltier_rest_s", handle_peltier_rest_s)


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
        elif cmd == "target_active":
            handle_target_active("/http", str(value))
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
        elif cmd == "unique_peltier":
            handle_unique_peltier("/http", int(bool(value)))
        elif cmd == "peltier_rest_s":
            handle_peltier_rest_s("/http", int(value))
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
        "active_target": active_target,
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
        "unique_peltier": int(unique_peltier),
        "peltier_rest_s": peltier_rest_s,
        # -1 sentinel keeps the field int-typed (OSC has no None / unknown).
        "active_peltier_index": active_peltier_index if active_peltier_index is not None else -1,
        # Per-cell countdown rides HTTP snapshot only (not the 5 Hz OSC tail).
        "peltier_rest_remaining": _peltier_rest_remaining_s(),
        "sensors_ok": any(t is not None for t in temp_c),
    }


def get_status_osc_args():
    """OSC argument list matching the documented /vents/status contract.
    Missing temperatures are encoded as -1.0 (python-osc rejects None).
    Backend `_handle_vents_status` parses arg 13 onward optionally so older
    firmware (12 args, no max_temp_c) through current (24 args) all decode.

    Positions 16-19 are the dual-setpoint tail (temp_hot_c, temp_cold_c,
    hot_target_c, cold_target_c). Position 20 is `active_target`. Positions
    21/22/23 are the unique-peltier tail (unique_peltier, peltier_rest_s,
    active_peltier_index). Admin builds older than this firmware simply stop
    reading earlier; `peltier_rest_remaining[3]` is HTTP-snapshot only."""
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
        str(s["active_target"]),
        int(s["unique_peltier"]),
        s["peltier_rest_s"],
        int(s["active_peltier_index"]),
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
        "active_target": active_target,
        "max_temp_c": max_temp_c,
        "probe_hot_id": probe_hot_id,
        "probe_cold_id": probe_cold_id,
    }
