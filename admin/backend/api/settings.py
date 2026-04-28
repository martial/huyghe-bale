"""Settings API routes."""

import json
import logging
import os
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request

from api.devices import store as device_store
from config import DATA_DIR
from storage.json_store import _write_atomic

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

VALID_BRIDGE_ROUTING = ("passthrough", "type-match", "none")

DEFAULTS = {
    "osc_frequency": 30,          # Hz — playback engine tick rate
    "bridge_enabled": False,      # OSC bridge: listen on a new port and fan out to devices
    "bridge_port": 9002,          # Bridge UDP listen port (1024–65535, != 9001 admin receiver)
    "bridge_routing": "type-match",  # "passthrough" | "type-match" | "none"
    # Absolute °C threshold for vents over-temp (persisted on each vents Pi when saved)
    "vents_max_temp_c": 80.0,
    # Minimum fan PWM (% duty) every vents Pi must hold whenever a non-zero
    # duty is requested — pushed to each Pi on save and persisted there.
    "vents_min_fan_pct": 20.0,
    # Maximum fan PWM (% duty). The Pi multiplies every non-zero fan command
    # by this/100 before applying the floor. Replaces the old admin-side
    # `output_cap` so the cap is enforced regardless of command source.
    "vents_max_fan_pct": 100.0,
    # Per-channel RPM threshold below which the OSC receiver flags an alarm
    # for that fan tach (admin-side only — the Pi does not need this value).
    "vents_min_rpm_alarm": 500,
    # Fan PWM (%) the Pi forces both fans to whenever any sensor exceeds
    # max_temp_c. Pushed to each Pi on save and persisted there.
    "vents_over_temp_fan_pct": 100.0,
}

# Listeners notified when specific settings change. Keys: setting name.
# Values: list of callables called with (old_value, new_value) after _write.
_change_listeners: "dict[str, list]" = {}


def on_change(key: str, callback):
    """Register a callback fired after `key` is written with a new value.
    Used by app boot to restart the bridge when its port / enable flips."""
    _change_listeners.setdefault(key, []).append(callback)


_KNOWN_KEYS = frozenset(DEFAULTS.keys())


def _read():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                # Drop retired keys (e.g. output_cap, replaced by the Pi-side
                # vents_max_fan_pct) so they don't linger in GET responses.
                merged = {**DEFAULTS, **json.load(f)}
                return {k: v for k, v in merged.items() if k in _KNOWN_KEYS}
        except (json.JSONDecodeError, OSError) as e:
            quarantine = f"{SETTINGS_FILE}.corrupted"
            try:
                os.replace(SETTINGS_FILE, quarantine)
                logger.warning(
                    "Corrupt settings file quarantined to %s (%s); reverting to defaults",
                    quarantine, e,
                )
            except OSError as rename_err:
                logger.warning(
                    "Corrupt settings file %s (%s); could not quarantine: %s",
                    SETTINGS_FILE, e, rename_err,
                )
    return dict(DEFAULTS)


def _write(data):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    _write_atomic(SETTINGS_FILE, data)


def _fire(key: str, old, new):
    for cb in _change_listeners.get(key, []):
        try:
            cb(old, new)
        except Exception:
            # A misbehaving listener must not wedge the settings PUT.
            pass


def _push_vents_command(command: str, value):
    """POST a {command, value} payload to every configured vents device's
    HTTP /gpio/test, so the Pi applies the new value and persists it."""
    payload = json.dumps({"command": command, "value": value}).encode("utf-8")
    for dev in device_store.list_all():
        if dev.get("type") != "vents":
            continue
        ip = dev.get("ip_address")
        if not ip:
            continue
        req = urllib.request.Request(
            f"http://{ip}:9001/gpio/test",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=4)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.warning("Push %s=%r to %s failed: %s", command, value, ip, e)


def _round2(v): return round(float(v), 2)


# (key, lo, hi, cast, unit). Validation table for vents numeric settings.
# Settings absent from `_VENTS_PUSHED_SETTINGS` below stay admin-side only.
_VENTS_NUMERIC_SETTINGS = (
    ("vents_max_temp_c",        -55,   125,   _round2, "°C"),
    ("vents_min_fan_pct",         0,   100,   _round2, ""),
    ("vents_max_fan_pct",         0,   100,   _round2, ""),
    ("vents_min_rpm_alarm",       0, 10000,   int,     "RPM"),
    ("vents_over_temp_fan_pct",   0,   100,   _round2, ""),
)

# Setting key → Pi /gpio/test command. Missing keys are admin-side only.
_VENTS_PUSHED_SETTINGS = {
    "vents_max_temp_c": "max_temp",
    "vents_min_fan_pct": "min_fan_pct",
    "vents_max_fan_pct": "max_fan_pct",
    "vents_over_temp_fan_pct": "over_temp_fan_pct",
}


@bp.route("", methods=["GET"])
def get_settings():
    return jsonify(_read())


@bp.route("", methods=["PUT"])
def update_settings():
    body = request.get_json() or {}
    current = _read()
    before = dict(current)

    if "osc_frequency" in body:
        val = body["osc_frequency"]
        if not isinstance(val, (int, float)) or val < 1 or val > 120:
            return jsonify({"error": "osc_frequency must be between 1 and 120 Hz"}), 400
        current["osc_frequency"] = int(val)

    if "bridge_enabled" in body:
        current["bridge_enabled"] = bool(body["bridge_enabled"])

    if "bridge_port" in body:
        val = body["bridge_port"]
        if not isinstance(val, int) or val < 1024 or val > 65535 or val == 9001:
            return jsonify({
                "error": "bridge_port must be 1024–65535 and not 9001 (admin receiver)"
            }), 400
        current["bridge_port"] = val

    if "bridge_routing" in body:
        val = body["bridge_routing"]
        if val not in VALID_BRIDGE_ROUTING:
            return jsonify({
                "error": f"bridge_routing must be one of {VALID_BRIDGE_ROUTING}"
            }), 400
        current["bridge_routing"] = val

    for key, lo, hi, cast, unit in _VENTS_NUMERIC_SETTINGS:
        if key not in body:
            continue
        val = body[key]
        if not isinstance(val, (int, float)) or val < lo or val > hi:
            return jsonify({"error": f"{key} must be between {lo} and {hi} {unit}".strip()}), 400
        current[key] = cast(val)

    _write(current)

    # Push device-side settings to every vents Pi when their values changed.
    for key, command in _VENTS_PUSHED_SETTINGS.items():
        if key in body and before.get(key) != current.get(key):
            _push_vents_command(command, current[key])

    # Admin-side alarm threshold lives only in the receiver — propagate it
    # immediately so the next status tick uses the new value.
    if "vents_min_rpm_alarm" in body and before.get("vents_min_rpm_alarm") != current.get("vents_min_rpm_alarm"):
        try:
            from engine.osc_receiver import OscReceiver
            OscReceiver().set_min_rpm_alarm(int(current["vents_min_rpm_alarm"]))
        except Exception as e:
            logger.warning("Could not propagate vents_min_rpm_alarm to receiver: %s", e)

    for key in ("bridge_enabled", "bridge_port", "bridge_routing"):
        if before.get(key) != current.get(key):
            _fire(key, before.get(key), current.get(key))

    return jsonify(current)
