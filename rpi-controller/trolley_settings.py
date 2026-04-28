"""Per-Pi trolley calibration + motor settings, persisted in device.json.

Read at module import / on demand to derive the runtime values used by
controllers.trolley:

  rail_length_steps     ground truth for /trolley/position 0..1 → step count
  soft_limit_pct        margin from the unprotected forward end
  calibration_direction "forward" or "reverse" — direction the carriage moves
                        during /trolley/calibrate. /trolley/home drives the
                        opposite way until the limit switch trips.
  calibration_speed_hz  pulse rate used during the calibration span pass
  max_speed_hz          ceiling for /trolley/position follow

The block lives at JSON path .trolley inside ~/.config/gpio-osc/device.json
(written by identity.py). Missing block → defaults are used and the trolley
reports calibrated=False.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(os.path.expanduser("~/.config/gpio-osc/device.json"))
_LOCK = threading.RLock()

DEFAULTS = {
    "rail_length_steps": None,         # None → uncalibrated
    "lead_mm_per_rev": 8.0,            # informational
    "steps_per_rev": 200,              # informational
    "microsteps": 16,                  # informational
    "max_speed_hz": 2000,
    "calibration_speed_hz": 600,
    "calibration_direction": "forward",  # also defines which DIR-pin level drives away from home
    "soft_limit_pct": 0.98,
    # When True, /trolley/position runs even on an unhomed/uncalibrated rig
    # (uses TROLLEY_MAX_STEPS as the rail length). For bench testing.
    "permissive_mode": True,
}

VALID_DIRECTIONS = ("forward", "reverse")
ALLOWED_KEYS = tuple(DEFAULTS.keys())


def _coerce(key, value):
    """Coerce/validate one setting. Raises ValueError on bad input."""
    if key == "rail_length_steps":
        if value is None:
            return None
        v = int(value)
        if v <= 0:
            raise ValueError("rail_length_steps must be > 0")
        return v
    if key == "lead_mm_per_rev":
        v = float(value)
        if v <= 0:
            raise ValueError("lead_mm_per_rev must be > 0")
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
    if key == "calibration_speed_hz":
        v = float(value)
        if v <= 0:
            raise ValueError("calibration_speed_hz must be > 0")
        return v
    if key == "calibration_direction":
        s = str(value).strip().lower()
        if s not in VALID_DIRECTIONS:
            raise ValueError("calibration_direction must be 'forward' or 'reverse'")
        return s
    if key == "soft_limit_pct":
        v = float(value)
        if not (0.0 < v <= 1.0):
            raise ValueError("soft_limit_pct must be in (0, 1]")
        return v
    if key == "permissive_mode":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        raise ValueError("permissive_mode must be a boolean")
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
    return settings.get("rail_length_steps") is not None


def soft_limit_steps(settings: dict) -> int:
    """Effective forward target ceiling (steps) for /trolley/position 1.0."""
    rail = settings.get("rail_length_steps")
    pct = settings.get("soft_limit_pct", DEFAULTS["soft_limit_pct"])
    if not rail:
        return 0
    return int(round(rail * pct))


def opposite_direction(direction: str) -> str:
    return "reverse" if direction == "forward" else "forward"
