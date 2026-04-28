"""Trolley test-panel API — send raw OSC commands and read last-seen status.

The UI's trolley panel calls:
  POST /api/v1/trolley-control/<device_id>/command  {command, value}
  GET  /api/v1/trolley-control/<device_id>/status

Raw commands translate directly to /trolley/<command> OSC messages. Status is
read from the OscReceiver's trolley_status dict, which is populated by the
Pi-pushed /trolley/status OSC broadcasts.
"""

import logging

from flask import Blueprint, request, jsonify

from api.devices import store as device_store
from engine.osc_sender import OscSender
from engine.osc_receiver import OscReceiver

logger = logging.getLogger(__name__)

bp = Blueprint("trolley_control", __name__)
_osc = OscSender()
_receiver = OscReceiver(port=9001)

# Maps user-facing command names → (OSC address, arg coercion).
# Calibration and config use slash-namespaced sub-addresses to stay tidy
# and avoid colliding with raw motion commands like "stop".
_COMMAND_MAP = {
    "enable":           ("/trolley/enable",           "int"),
    "dir":              ("/trolley/dir",              "int"),
    "speed":            ("/trolley/speed",            "float"),
    "step":             ("/trolley/step",             "int"),
    "stop":             ("/trolley/stop",             "int_or_zero"),
    "home":             ("/trolley/home",             "int_or_zero"),
    "position":         ("/trolley/position",         "float"),
    "calibrate_start":  ("/trolley/calibrate/start",  "string_or_zero"),
    "calibrate_stop":   ("/trolley/calibrate/stop",   "int_or_zero"),
    "calibrate_save":   ("/trolley/calibrate/save",   "int_or_zero"),
    "calibrate_cancel": ("/trolley/calibrate/cancel", "int_or_zero"),
    "config_save":      ("/trolley/config/save",      "int_or_zero"),
    "config_get":       ("/trolley/config/get",       "int_or_zero"),
    # config_set is special-cased below (two args: key, value).
}


def _coerce(value, kind):
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "int_or_zero":
        return int(value) if value else 0
    if kind == "string_or_zero":
        # Used for /trolley/calibrate/start which takes an optional direction
        # string. Anything falsy → send int 0 so the firmware treats it as "no
        # direction override". Strings pass through as-is.
        if not value:
            return 0
        return str(value)
    raise ValueError(f"unknown coercion: {kind!r}")


@bp.route("/<device_id>/command", methods=["POST"])
def send_command(device_id):
    body = request.get_json() or {}
    command = body.get("command")

    device = device_store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    if device.get("type") != "trolley":
        return jsonify({"error": "Device is not a trolley"}), 400

    ip = device.get("ip_address")
    port = device.get("osc_port", 9000)
    if not ip:
        return jsonify({"error": "Device has no IP address"}), 400

    # config_set is the only multi-arg command on this surface.
    if command == "config_set":
        key = body.get("key")
        value = body.get("value")
        if not key:
            return jsonify({"error": "config_set requires 'key'"}), 400
        try:
            _osc.send(ip, port, "/trolley/config/set", [str(key), value])
            return jsonify({"ok": True, "sent": {
                "address": "/trolley/config/set", "key": key, "value": value,
            }})
        except Exception as e:
            logger.warning("Trolley config_set to %s failed: %s", ip, e)
            return jsonify({"ok": False, "error": str(e)}), 502

    if command not in _COMMAND_MAP:
        return jsonify({"error": f"unknown command: {command!r}"}), 400

    address, kind = _COMMAND_MAP[command]
    raw = body.get("value", 0)
    try:
        value = _coerce(raw, kind)
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"bad value for {command}: {e}"}), 400

    try:
        _osc.send(ip, port, address, value)
        return jsonify({"ok": True, "sent": {"address": address, "value": value}})
    except Exception as e:
        logger.warning("Trolley command to %s failed: %s", ip, e)
        return jsonify({"ok": False, "error": str(e)}), 502


@bp.route("/<device_id>/status", methods=["GET"])
def get_status(device_id):
    device = device_store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    ip = device.get("ip_address")
    if not ip:
        return jsonify({"position": 0.0, "limit": 0, "homed": 0, "online": False})

    # The trolleys page doesn't open the /devices SSE stream, so nobody is
    # broadcasting /sys/ping. Send one on each status poll so the Pi's last_seen
    # stays fresh (keeping `online` true and triggering the Pi's /trolley/status
    # broadcast loop). Fire-and-forget.
    port = device.get("osc_port", 9000)
    try:
        _osc.send(ip, port, "/sys/ping", _receiver.port)
    except Exception as e:
        logger.debug("ping on status poll failed: %s", e)

    status = _receiver.get_trolley_status(ip)
    online = _receiver.get_status(ip, timeout=6.0)
    return jsonify({
        "position": status.get("position", 0.0),
        "limit": status.get("limit", 0),
        "homed": status.get("homed", 0),
        "calibrated": status.get("calibrated", 0),
        "state": status.get("state", "idle"),
        "timestamp": status.get("timestamp"),
        "online": online,
    })
