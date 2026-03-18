"""Device API routes."""

import json
import time
import logging

from flask import Blueprint, request, jsonify, Response
from storage.json_store import JsonStore
from engine.osc_sender import OscSender
from engine.osc_receiver import OscReceiver
from engine.network_scanner import scan_subnet_stream
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
    """SSE endpoint streaming online/offline status for all devices."""
    def generate():
        last_ping_time = 0
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

            logger.debug("Device statuses: %s (last_seen: %s)", statuses, receiver.last_seen)
            yield f"data: {json.dumps(statuses)}\n\n"
            time.sleep(1.0)

    return Response(generate(), mimetype="text/event-stream")


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
