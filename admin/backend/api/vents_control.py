"""Vents device-panel API — send raw OSC commands and read live status.

Mirrors api/trolley_control.py. Commands map directly to /vents/<address>:

  POST /api/v1/vents-control/<device_id>/command
       {command: "peltier" | "peltier_mask" | "fan" | "mode" | "target" | "max_temp",
        index?: 1|2|3 (peltier) or 1|2 (fan),
        value: ...}

  GET  /api/v1/vents-control/<device_id>/status
       → {temp1_c, temp2_c, fan1, fan2, peltier_mask, peltier,
          rpm1A..rpm2B, target_c, max_temp_c?, mode, state, online, timestamp}
"""

import logging

from flask import Blueprint, request, jsonify

from api.devices import store as device_store
from engine.osc_sender import OscSender
from engine.osc_receiver import OscReceiver

logger = logging.getLogger(__name__)

bp = Blueprint("vents_control", __name__)
_osc = OscSender()
_receiver = OscReceiver(port=9001)

_VALID_COMMANDS = ("peltier", "peltier_mask", "fan", "mode", "target", "max_temp")


def _route(command, body):
    """Translate an admin command into (address, value) for the Pi."""
    value = body.get("value")
    if command == "peltier":
        idx = int(body.get("index", 1))
        if idx not in (1, 2, 3):
            raise ValueError("peltier index must be 1, 2 or 3")
        return f"/vents/peltier/{idx}", int(bool(int(value)))
    if command == "peltier_mask":
        return "/vents/peltier", int(value) & 0b111
    if command == "fan":
        idx = int(body.get("index", 1))
        if idx not in (1, 2):
            raise ValueError("fan index must be 1 or 2")
        return f"/vents/fan/{idx}", max(0.0, min(1.0, float(value)))
    if command == "mode":
        v = str(value).strip().lower()
        if v not in ("raw", "auto"):
            raise ValueError("mode must be 'raw' or 'auto'")
        return "/vents/mode", v
    if command == "target":
        return "/vents/target", float(value)
    if command == "max_temp":
        return "/vents/max_temp", float(value)
    raise ValueError(f"unknown command: {command!r}")


@bp.route("/<device_id>/command", methods=["POST"])
def send_command(device_id):
    body = request.get_json() or {}
    command = body.get("command")
    if command not in _VALID_COMMANDS:
        return jsonify({"error": f"unknown command: {command!r}"}), 400

    device = device_store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    if device.get("type") != "vents":
        return jsonify({"error": "Device is not a vents"}), 400

    ip = device.get("ip_address")
    port = device.get("osc_port", 9000)
    if not ip:
        return jsonify({"error": "Device has no IP address"}), 400

    try:
        address, value = _route(command, body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        _osc.send(ip, port, address, value)
        return jsonify({"ok": True, "sent": {"address": address, "value": value}})
    except Exception as e:
        logger.warning("Vents command to %s failed: %s", ip, e)
        return jsonify({"ok": False, "error": str(e)}), 502


@bp.route("/<device_id>/status", methods=["GET"])
def get_status(device_id):
    device = device_store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    ip = device.get("ip_address")
    if not ip:
        return jsonify({"online": False})

    # Same trick as trolley-control: broadcast a ping on each poll so the Pi's
    # last_seen stays fresh and it keeps pushing /vents/status back to us.
    port = device.get("osc_port", 9000)
    try:
        _osc.send(ip, port, "/sys/ping", _receiver.port)
    except Exception as e:
        logger.debug("ping on status poll failed: %s", e)

    snap = _receiver.get_vents_status(ip)
    online = _receiver.get_status(ip, timeout=6.0)
    return jsonify({**snap, "online": online})
