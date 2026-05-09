"""Per-Pi trolley configuration, persisted in device.json.

Read at module import / on demand to derive the runtime values used by
controllers.trolley.

The rail length in steps is **derived** from the physical configuration
(rail length + wheel radius) plus the motor parameters (steps_per_rev,
microsteps). There is no longer a calibration span pass — the operator
enters the two physical measurements and the firmware computes everything.

  rail_length_mm       physical rail travel between the two end-stops
  wheel_radius_mm      pitch radius of the drive pulley/wheel
  steps_per_rev        motor full-step count (NEMA 34 = 200)
  microsteps           CL86Y dip-switch setting

  travel_per_rev_mm    = 2 * π * wheel_radius_mm
  steps_per_mm         = (steps_per_rev * microsteps) / travel_per_rev_mm
  rail_length_steps    = round(rail_length_mm * steps_per_mm)

Other knobs:

  soft_limit_pct        margin from the unprotected forward end
  calibration_direction "forward" or "reverse" — wiring polarity. Defines
                        which DIR-pin level drives the carriage *away* from
                        the home end-stop.
  home_speed_hz         pulse rate used by /trolley/home
  max_speed_hz          ceiling for /trolley/position follow

The block lives at JSON path .trolley inside ~/.config/gpio-osc/device.json
(written by identity.py). Missing block → defaults are used and the trolley
reports calibrated=False.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(os.path.expanduser("~/.config/gpio-osc/device.json"))
_LOCK = threading.RLock()

DEFAULTS = {
    "rail_length_mm": None,            # None → unconfigured
    "wheel_radius_mm": None,           # None → unconfigured
    "steps_per_rev": 200,
    "microsteps": 16,
    "max_speed_hz": 2000,
    "home_speed_hz": 100,
    "calibration_direction": "forward",  # wiring polarity for "away from home"
    # Swap which physical limit-switch pin acts as home vs far. Defaults to
    # True for this project's wiring (home switch is on PIN_LIM_SWITCH_FAR /
    # BCM 21, far switch on PIN_LIM_SWITCH / BCM 20). Set False on rigs that
    # wire the home switch to PIN_LIM_SWITCH directly.
    # Takes effect on service restart (ISR registration is at setup time).
    "limit_switches_swapped": True,
    # CL86Y ALARM optocoupler polarity. Defaults to "disabled" because the
    # rig wiring/polarity hasn't been verified end-to-end yet — turning the
    # auto-lock on with the wrong polarity bricks motion at boot.
    #   "active_high" — pin reads HIGH on fault
    #   "active_low"  — pin reads LOW on fault (HIGH = OK)
    #   "disabled"    — ignore alarm pins entirely (no auto-lock)
    "alarm_polarity": "disabled",
    "soft_limit_pct": 0.98,
    # When True, /trolley/position runs even on an unconfigured rig
    # (uses TROLLEY_MAX_STEPS as the rail length). For bench testing.
    "permissive_mode": True,
    # Trapezoidal ramp times applied to /trolley/step and /trolley/position.
    # 0 = no ramp (constant speed, identical to legacy behaviour).
    "accel_time_s": 0.0,
    "decel_time_s": 0.0,
}

VALID_DIRECTIONS = ("forward", "reverse")
VALID_ALARM_POLARITIES = ("active_high", "active_low", "disabled")
ALLOWED_KEYS = tuple(DEFAULTS.keys())


def _coerce(key, value):
    """Coerce/validate one setting. Raises ValueError on bad input."""
    if key in ("rail_length_mm", "wheel_radius_mm"):
        if value is None:
            return None
        v = float(value)
        if v <= 0:
            raise ValueError(f"{key} must be > 0")
        return v
    if key == "steps_per_rev":
        v = int(value)
        if v <= 0:
            raise ValueError("steps_per_rev must be > 0")
        return v
    if key == "microsteps":
        v = int(value)
        if v <= 0:
            raise ValueError("microsteps must be > 0")
        return v
    if key == "max_speed_hz":
        v = float(value)
        if v <= 0:
            raise ValueError("max_speed_hz must be > 0")
        return v
    if key == "home_speed_hz":
        v = float(value)
        if v <= 0:
            raise ValueError("home_speed_hz must be > 0")
        return v
    if key == "calibration_direction":
        s = str(value).strip().lower()
        if s not in VALID_DIRECTIONS:
            raise ValueError("calibration_direction must be 'forward' or 'reverse'")
        return s
    if key == "alarm_polarity":
        s = str(value).strip().lower()
        if s not in VALID_ALARM_POLARITIES:
            raise ValueError(
                "alarm_polarity must be one of: " + ", ".join(VALID_ALARM_POLARITIES)
            )
        return s
    if key == "soft_limit_pct":
        v = float(value)
        if not (0.0 < v <= 1.0):
            raise ValueError("soft_limit_pct must be in (0, 1]")
        return v
    if key in ("accel_time_s", "decel_time_s"):
        v = float(value)
        if not (0.0 <= v <= 10.0):
            raise ValueError(f"{key} must be in [0, 10] seconds")
        return v
    if key in ("permissive_mode", "limit_switches_swapped"):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        raise ValueError(f"{key} must be a boolean")
    raise ValueError(f"unknown setting: {key!r}")


def _read_file() -> dict:
    try:
        return json.loads(_PATH.read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("trolley_settings: cannot read %s: %s", _PATH, e)
        return {}


def _write_file(doc: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(doc, indent=2) + "\n")


def load() -> dict:
    """Return a full settings dict (defaults + persisted overrides)."""
    with _LOCK:
        doc = _read_file()
        block = doc.get("trolley") or {}
        result = dict(DEFAULTS)
        for k in ALLOWED_KEYS:
            if k in block:
                try:
                    result[k] = _coerce(k, block[k])
                except Exception as e:
                    logger.warning("trolley_settings: bad %s=%r in device.json: %s", k, block[k], e)
        return result


def save(settings: dict) -> dict:
    """Validate + persist the given settings dict (full block)."""
    with _LOCK:
        validated = {}
        for k in ALLOWED_KEYS:
            if k in settings:
                validated[k] = _coerce(k, settings[k])
            else:
                validated[k] = DEFAULTS[k]
        doc = _read_file()
        doc["trolley"] = validated
        _write_file(doc)
        return validated


def update(key: str, value):
    """Coerce-and-validate a single key without persisting. Returns the value."""
    return _coerce(key, value)


def is_calibrated(settings: dict) -> bool:
    """True when both physical measurements are set — rail steps can be derived."""
    return bool(settings.get("rail_length_mm")) and bool(settings.get("wheel_radius_mm"))


def derived_rail_length_steps(settings: dict) -> int:
    """Compute total step count between home and far end.

    Returns 0 when either physical input is missing.
    """
    rail_mm = settings.get("rail_length_mm")
    wheel_mm = settings.get("wheel_radius_mm")
    if not rail_mm or not wheel_mm:
        return 0
    steps_per_rev = int(settings.get("steps_per_rev") or DEFAULTS["steps_per_rev"])
    microsteps = int(settings.get("microsteps") or DEFAULTS["microsteps"])
    travel_per_rev_mm = 2.0 * math.pi * float(wheel_mm)
    steps_per_mm = (steps_per_rev * microsteps) / travel_per_rev_mm
    return int(round(float(rail_mm) * steps_per_mm))


def soft_limit_steps(settings: dict) -> int:
    """Effective forward target ceiling (steps) for /trolley/position 1.0."""
    rail = derived_rail_length_steps(settings)
    pct = settings.get("soft_limit_pct", DEFAULTS["soft_limit_pct"])
    if not rail:
        return 0
    return int(round(rail * pct))


def opposite_direction(direction: str) -> str:
    return "reverse" if direction == "forward" else "forward"
