"""Settings API routes."""

import json
import logging
import os

from flask import Blueprint, jsonify, request

from config import DATA_DIR
from storage.json_store import _write_atomic

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

VALID_BRIDGE_ROUTING = ("passthrough", "type-match", "none")

DEFAULTS = {
    "osc_frequency": 30,          # Hz — playback engine tick rate
    "output_cap": 100,            # Max output percentage (1–100)
    "bridge_enabled": False,      # OSC bridge: listen on a new port and fan out to devices
    "bridge_port": 9002,          # Bridge UDP listen port (1024–65535, != 9001 admin receiver)
    "bridge_routing": "type-match",  # "passthrough" | "type-match" | "none"
}

# Listeners notified when specific settings change. Keys: setting name.
# Values: list of callables called with (old_value, new_value) after _write.
_change_listeners: "dict[str, list]" = {}


def on_change(key: str, callback):
    """Register a callback fired after `key` is written with a new value.
    Used by app boot to restart the bridge when its port / enable flips."""
    _change_listeners.setdefault(key, []).append(callback)


def _read():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                return {**DEFAULTS, **json.load(f)}
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

    if "output_cap" in body:
        val = body["output_cap"]
        if not isinstance(val, (int, float)) or val < 1 or val > 100:
            return jsonify({"error": "output_cap must be between 1 and 100"}), 400
        current["output_cap"] = int(val)

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

    _write(current)

    for key in ("bridge_enabled", "bridge_port", "bridge_routing"):
        if before.get(key) != current.get(key):
            _fire(key, before.get(key), current.get(key))

    return jsonify(current)
