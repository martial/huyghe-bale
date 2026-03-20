"""Device API routes."""

import json
import time
import logging
import urllib.request

from flask import Blueprint, request, jsonify, Response
from storage.json_store import JsonStore
from engine.osc_sender import OscSender
from engine.osc_receiver import OscReceiver
from engine.network_scanner import scan_subnet_stream
from engine.version_checker import get_latest_version, invalidate_cache as invalidate_version_cache
from config import DATA_DIR

logger = logging.getLogger(__name__)

bp = Blueprint("devices", __name__)
store = JsonStore(DATA_DIR, "devices", "dev")
osc = OscSender()
receiver = OscReceiver(port=9001)


@bp.route("", methods=["GET"])
def list_devices():
    return jsonify(store.list_all())


@bp.route("", methods=["POST"])
def create_device():
    data = request.get_json() or {}
    device = {
        "name": data.get("name", "Untitled"),
        "ip_address": data.get("ip_address", ""),
        "osc_port": data.get("osc_port", 9000),
    }
    if "id" in data:
        device["id"] = data["id"]
    return jsonify(store.create(device)), 201


@bp.route("/test-send", methods=["POST"])
def test_send():
    """Send test values to devices via OSC or HTTP."""
    data = request.get_json() or {}
    device_ids = data.get("device_ids", [])
    value_a = max(0.0, min(1.0, float(data.get("value_a", 0.0))))
    value_b = max(0.0, min(1.0, float(data.get("value_b", 0.0))))
    method = data.get("method", "osc")

    results = {}
    for did in device_ids:
        device = store.get(did)
        if not device:
            results[did] = {"ok": False, "error": "not found"}
            continue
        ip = device.get("ip_address")
        if not ip:
            results[did] = {"ok": False, "error": "no ip"}
            continue

        try:
            if method == "http":
                body = json.dumps({"value_a": value_a, "value_b": value_b}).encode()
                req = urllib.request.Request(
                    f"http://{ip}:9001/gpio/test",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    results[did] = json.loads(resp.read())
            else:
                port = device.get("osc_port", 9000)
                osc.send(ip, port, "/gpio/a", value_a)
                osc.send(ip, port, "/gpio/b", value_b)
                results[did] = {"ok": True, "sent_a": value_a, "sent_b": value_b}
        except Exception as e:
            logger.warning("Test send to %s (%s) failed: %s", did, method, e)
            results[did] = {"ok": False, "error": str(e)}

    return jsonify({"ok": True, "results": results})


@bp.route("/scan", methods=["POST"])
def scan_network():
    data = request.get_json(silent=True) or {}
    subnet = data.get("subnet") or None
    existing_ips = {d["ip_address"] for d in store.list_all()}

    def generate():
        try:
            for event in scan_subnet_stream(subnet):
                if event["type"] == "host" and event["ip"] in existing_ips:
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/status", methods=["GET"])
def device_status_stream():
    """SSE endpoint streaming online/offline status + versions for all devices."""
    def generate():
        last_ping_time = 0
        last_version_check = 0
        cached_versions = {}
        cached_system_info = {}
        logger.info("SSE status stream started")
        while True:
            now = time.time()

            devices = store.list_all()

            # Periodically broadcast ping to all devices
            if now - last_ping_time > 5.0:
                last_ping_time = now
                logger.info("Sending /sys/ping to %d device(s)", len(devices))
                for device in devices:
                    if ip := device.get("ip_address"):
                        try:
                            port = device.get("osc_port", 9000)
                            osc.send(ip, port, "/sys/ping", 9001)
                        except Exception as e:
                            logger.warning("  Ping failed for %s: %s", ip, e)

            # Yield online/offline based on pong received within timeout
            statuses = {}
            for device in devices:
                if ip := device.get("ip_address"):
                    pong = receiver.get_status(ip, timeout=6.0)
                    statuses[device["id"]] = "online" if pong else "offline"

            # Periodically fetch version from online devices via HTTP
            # Check every 5s until we have at least one version, then every 30s
            version_interval = 30.0 if cached_versions else 5.0
            if now - last_version_check > version_interval:
                last_version_check = now
                for device in devices:
                    if statuses.get(device["id"]) != "online":
                        continue
                    ip = device.get("ip_address")
                    if not ip:
                        continue
                    try:
                        req = urllib.request.urlopen(
                            f"http://{ip}:9001/status", timeout=2
                        )
                        data = json.loads(req.read())
                        cached_versions[device["id"]] = {
                            "version": data.get("version", "unknown"),
                            "version_date": data.get("version_date", "unknown"),
                        }
                        if "system_info" in data:
                            cached_system_info[device["id"]] = data["system_info"]
                    except Exception:
                        pass

            logger.debug("Device statuses: %s (last_seen: %s)", statuses, receiver.last_seen)
            yield f"data: {json.dumps({'statuses': statuses, 'versions': cached_versions, 'system_info': cached_system_info})}\n\n"
            time.sleep(1.0)

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/version/latest", methods=["GET"])
def latest_version():
    """Return latest commit info from GitHub."""
    return jsonify(get_latest_version())


@bp.route("/<device_id>", methods=["GET"])
def get_device(device_id):
    device = store.get(device_id)
    if not device:
        return jsonify({"error": "Not found"}), 404
    return jsonify(device)


@bp.route("/<device_id>", methods=["PUT"])
def update_device(device_id):
    data = request.get_json() or {}
    updated = store.update(device_id, data)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    return jsonify(updated)


@bp.route("/<device_id>", methods=["DELETE"])
def delete_device(device_id):
    if store.delete(device_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@bp.route("/<device_id>/ping", methods=["POST"])
def ping_device(device_id):
    device = store.get(device_id)
    if not device:
        return jsonify({"error": "Not found"}), 404
    try:
        # Pinging explicitly sets off a `/sys/ping`
        osc.send(device["ip_address"], device.get("osc_port", 9000), "/sys/ping", 9001)
        return jsonify({"ok": True, "message": "Ping sent"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@bp.route("/<device_id>/update", methods=["POST"])
def update_device_software(device_id):
    """Proxy update request to device's HTTP server."""
    device = store.get(device_id)
    if not device:
        return jsonify({"error": "Not found"}), 404
    ip = device.get("ip_address")
    if not ip:
        return jsonify({"error": "No IP address configured"}), 400
    try:
        req = urllib.request.Request(
            f"http://{ip}:9001/update", method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            if data.get("success"):
                invalidate_version_cache()
            return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "logs": str(e), "new_version": "unknown"}), 502
