"""Docs / protocol quick-test API — OSC to Pi, HTTP proxy to Pi :9001, OSC to Bridge loopback."""

import json
import logging
import urllib.request
from typing import Any, List, Optional

from flask import Blueprint, jsonify, request

from api import devices as devices_api
from api.settings import _read as read_settings
from engine.osc_sender import OscSender

logger = logging.getLogger(__name__)

bp = Blueprint("protocol_test", __name__)
_osc = OscSender()

ALLOW_HTTP_GET = frozenset({"/status"})
ALLOW_HTTP_POST = frozenset({"/gpio/test", "/update"})


def _validate_address_prefix(address: str, device_type: str) -> Optional[str]:
    """Return error message if address prefix does not match device type."""
    if not address.startswith("/"):
        return "address must start with /"
    if address.startswith("/sys/"):
        return None
    if address.startswith("/vents/"):
        if device_type != "vents":
            return "address is vents-only but device is not type vents"
        return None
    if address.startswith("/trolley/"):
        if device_type != "trolley":
            return "address is trolley-only but device is not type trolley"
        return None
    return "address prefix must be /sys/, /vents/, or /trolley/"


def _coerce_values(raw: Any) -> List[Any]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("values must be a JSON array")
    return list(raw)


@bp.route("/osc", methods=["POST"])
def send_osc():
    """POST JSON: { device_id, address, values?: [...] }. Send OSC to device's osc_port."""
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    addr = body.get("address")
    if not device_id or not isinstance(device_id, str):
        return jsonify({"error": "device_id required"}), 400
    if not addr or not isinstance(addr, str):
        return jsonify({"error": "address required"}), 400

    device = devices_api.store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    dtype = device.get("type") or "vents"
    err = _validate_address_prefix(addr, dtype)
    if err:
        return jsonify({"error": err}), 400

    ip = device.get("ip_address")
    if not ip:
        return jsonify({"error": "Device has no IP address"}), 400
    port = int(device.get("osc_port") or 9000)

    try:
        vals = _coerce_values(body.get("values"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        _osc.send_values(ip, port, addr, vals)
        return jsonify({"ok": True, "sent": {"address": addr, "values": vals}})
    except Exception as e:
        logger.warning("protocol-test OSC to %s failed: %s", ip, e)
        return jsonify({"ok": False, "error": str(e)}), 502


@bp.route("/http", methods=["POST"])
def proxy_http():
    """POST JSON: { device_id, method: GET|POST, path, json?: object } — Pi HTTP allow-list only."""
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id")
    method = (body.get("method") or "").upper()
    path = body.get("path")

    if not device_id or not isinstance(device_id, str):
        return jsonify({"error": "device_id required"}), 400
    if method not in ("GET", "POST"):
        return jsonify({"error": 'method must be "GET" or "POST"'}), 400
    if not path or not isinstance(path, str):
        return jsonify({"error": "path required"}), 400
    if not path.startswith("/"):
        path = "/" + path

    if method == "GET":
        if path not in ALLOW_HTTP_GET:
            return jsonify({"error": f"path not allowed for GET: {path}"}), 400
    else:
        if path not in ALLOW_HTTP_POST:
            return jsonify({"error": f"path not allowed for POST: {path}"}), 400

    device = devices_api.store.get(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    ip = device.get("ip_address")
    if not ip:
        return jsonify({"error": "Device has no IP address"}), 400

    url = f"http://{ip}:9001{path}"

    try:
        if method == "GET":
            req = urllib.request.Request(url, method="GET")
        else:
            payload = body.get("json")
            data = json.dumps(payload if payload is not None else {}).encode()
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
        timeout = 120 if path == "/update" else 15
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type") or ""
            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            return jsonify(
                {
                    "ok": True,
                    "status": resp.status,
                    "content_type": ct,
                    "body": parsed if parsed is not None else text[:8000],
                }
            )
    except Exception as e:
        logger.warning("protocol-test HTTP proxy %s %s failed: %s", method, url, e)
        return jsonify({"ok": False, "error": str(e)}), 502


@bp.route("/bridge", methods=["POST"])
def send_bridge():
    """POST JSON: simulate external OSC hitting the Bridge.

    Modes:
    - { address, values? } — send OSC to localhost:bridge_port (full address).
    - { inner_address, device_id, values? } — send /to/<device_id>/<inner_address>.
    """
    settings = read_settings()
    if not settings.get("bridge_enabled"):
        return jsonify({"error": "Bridge is disabled in Settings"}), 503

    bridge_port = int(settings.get("bridge_port") or 9002)

    body = request.get_json(silent=True) or {}
    inner = body.get("inner_address")
    device_id = body.get("device_id")
    addr = body.get("address")

    try:
        vals = _coerce_values(body.get("values"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if inner:
        if not device_id:
            return jsonify({"error": "device_id required when using inner_address"}), 400
        device = devices_api.store.get(device_id)
        if not device:
            return jsonify({"error": "Device not found"}), 404
        ia = inner if isinstance(inner, str) else ""
        if not ia.startswith("/"):
            ia = "/" + ia
        addr = f"/to/{device_id}{ia}"
    elif addr:
        if not isinstance(addr, str) or not addr.startswith("/"):
            return jsonify({"error": 'address must start with /'}), 400
    else:
        return jsonify({"error": "provide address or inner_address"}), 400

    try:
        _osc.send_values("127.0.0.1", bridge_port, addr, vals)
        return jsonify({"ok": True, "sent": {"address": addr, "values": vals, "bridge_port": bridge_port}})
    except Exception as e:
        logger.warning("protocol-test Bridge send failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 502
