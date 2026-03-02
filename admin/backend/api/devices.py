"""Device API routes."""

import json

from flask import Blueprint, request, jsonify, Response
from storage.json_store import JsonStore
from engine.osc_sender import OscSender
from engine.network_scanner import scan_subnet_stream
from config import DATA_DIR

bp = Blueprint("devices", __name__)
store = JsonStore(DATA_DIR, "devices", "dev")
osc = OscSender()


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
        osc.send(device["ip_address"], device.get("osc_port", 9000), "/gpio/a", 0.0)
        return jsonify({"ok": True, "message": "OSC packet sent"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500
