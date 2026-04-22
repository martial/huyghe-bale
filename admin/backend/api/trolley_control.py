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

_VALID_COMMANDS = ("enable", "dir", "speed", "step", "stop", "home", "position")


@bp.route("/<device_id>/command", methods=["POST"])
def send_command(device_id):
    body = request.get_json() or {}
    command = body.get("command")
    if command not in _VALID_COMMANDS:
        return jsonify({"error": f"unknown command: {command!r}"}), 400

    device = device_store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    if device.get("type") != "trolley":
        return jsonify({"error": "Device is not a trolley"}), 400

    ip = device.get("ip_address")
    port = device.get("osc_port", 9000)
    if not ip:
        return jsonify({"error": "Device has no IP address"}), 400

    address = f"/trolley/{command}"
    value = body.get("value", 0)
    # python-osc types are inferred from the Python value; coerce per-command
    # so the Pi sees the type it expects.
    if command in ("enable", "dir", "step"):
        value = int(value)
    elif command in ("speed", "position"):
        value = float(value)
    elif command in ("stop", "home"):
        value = int(value) if value else 0

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
    status = _receiver.get_trolley_status(ip)
    online = _receiver.get_status(ip, timeout=6.0)
    return jsonify({
        "position": status.get("position", 0.0),
        "limit": status.get("limit", 0),
        "homed": status.get("homed", 0),
        "timestamp": status.get("timestamp"),
        "online": online,
    })
