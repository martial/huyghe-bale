"""Vents device-panel API — send raw OSC commands and read live status.

Mirrors api/trolley_control.py. Commands map directly to /vents/<address>:

  POST /api/v1/vents-control/<device_id>/command
       {command: "peltier" | "peltier_mask" | "fan" | "mode"
                | "target" | "target_hot" | "target_cold" | "max_temp"
                | "probe_assign_hot" | "probe_assign_cold" | "probe_clear",
        index?: 1|2|3 (peltier) or 1|2 (fan),
        value: ...}

  GET  /api/v1/vents-control/<device_id>/status
       → {temp1_c, temp2_c, fan1, fan2, peltier_mask, peltier,
          rpm1A..rpm2B, target_c, hot_target_c, cold_target_c,
          temp_hot_c, temp_cold_c, probe_hot_id, probe_cold_id,
          probes, max_temp_c?, mode, state, online, timestamp}

  The probes[] list is fetched fresh from the Pi over HTTP each call (1 s
  timeout, 2 s in-process cache per IP) since the OSC broadcast can't carry
  a variable-length array of strings + temps.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request

from flask import Blueprint, request, jsonify

from api.devices import store as device_store
from config import DEFAULT_PI_HTTP_PORT
from engine.osc_sender import OscSender
from engine.osc_receiver import OscReceiver

logger = logging.getLogger(__name__)

bp = Blueprint("vents_control", __name__)
_osc = OscSender()
_receiver = OscReceiver(port=9001)

_VALID_COMMANDS = (
    "peltier", "peltier_mask", "fan", "mode",
    "target", "target_hot", "target_cold", "max_temp",
    "probe_assign_hot", "probe_assign_cold", "probe_clear",
)

import re as _re
_ROM_ID_RE = _re.compile(r"^28-[0-9a-fA-F]{12}$")
_PROBE_CLEAR_VALUES = ("hot", "cold", "both")


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
    if command == "target_hot":
        return "/vents/target/hot", float(value)
    if command == "target_cold":
        return "/vents/target/cold", float(value)
    if command == "max_temp":
        return "/vents/max_temp", float(value)
    if command in ("probe_assign_hot", "probe_assign_cold"):
        if not isinstance(value, str) or not _ROM_ID_RE.match(value.strip()):
            raise ValueError("rom_id must match 28-xxxxxxxxxxxx")
        suffix = "assign_hot" if command == "probe_assign_hot" else "assign_cold"
        return f"/vents/probe/{suffix}", value.strip()
    if command == "probe_clear":
        v = str(value).strip().lower()
        if v not in _PROBE_CLEAR_VALUES:
            raise ValueError("probe_clear must be 'hot', 'cold' or 'both'")
        return "/vents/probe/clear", v
    raise ValueError(f"unknown command: {command!r}")


# In-process snapshot cache: ip -> (timestamp, payload). Avoids hammering
# the Pi's HTTP endpoint when the admin polls /status faster than probe
# data actually changes.
_SNAPSHOT_TTL_S = 2.0
_snapshot_cache: dict = {}
_snapshot_lock = threading.Lock()


def _fetch_snapshot(ip):
    """POST {"command": "snapshot"} to the Pi's /gpio/test endpoint and
    return its JSON body. Cached for _SNAPSHOT_TTL_S seconds per IP. On
    network failure returns None so the caller can fall back to the OSC
    snapshot alone."""
    now = time.time()
    with _snapshot_lock:
        cached = _snapshot_cache.get(ip)
        if cached and now - cached[0] < _SNAPSHOT_TTL_S:
            return cached[1]
    try:
        body = json.dumps({"command": "snapshot"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://{ip}:{DEFAULT_PI_HTTP_PORT}/gpio/test",
            data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, ValueError) as e:
        logger.debug("snapshot fetch from %s failed: %s", ip, e)
        return None
    with _snapshot_lock:
        _snapshot_cache[ip] = (now, payload)
    return payload


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


_PROBE_FIELDS = (
    "probes", "probe_hot_id", "probe_cold_id",
    "temp_hot_c", "temp_cold_c",
    "hot_target_c", "cold_target_c",
)


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

    # Pull probes[] (and authoritative dual-setpoint fields) from the Pi's
    # HTTP snapshot. Cached 2 s/IP. Skipped when the device is offline —
    # there's no Pi to talk to, and we don't want to block the admin poll
    # waiting for a connect timeout.
    if online:
        full = _fetch_snapshot(ip)
        if full:
            for k in _PROBE_FIELDS:
                if k in full:
                    snap[k] = full[k]
    return jsonify({**snap, "online": online})
