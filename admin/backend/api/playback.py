"""Playback API routes."""

from flask import Blueprint, request, jsonify
from storage.json_store import JsonStore
from config import DATA_DIR
from api.settings import _read as read_settings
from engine.osc_receiver import OscReceiver

bp = Blueprint("playback", __name__)

# Legacy timeline + orchestration playback use /gpio/a + /gpio/b (vents-only).
# Trolley timelines go through a separate schema and /trolley/position.
PLAYBACK_DEVICE_TYPE = "vents"
TROLLEY_DEVICE_TYPE = "trolley"

timeline_store = JsonStore(DATA_DIR, "timelines", "tl")
device_store = JsonStore(DATA_DIR, "devices", "dev")
orchestration_store = JsonStore(DATA_DIR, "orchestrations", "orch")
trolley_timeline_store = JsonStore(DATA_DIR, "trolley_timelines", "trtl")

# The playback engine is set by the app on startup
_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


@bp.route("/start", methods=["POST"])
def start_playback():
    data = request.get_json() or {}
    playback_type = data.get("type")
    playback_id = data.get("id")
    device_ids = data.get("device_ids", [])

    if not playback_type or not playback_id:
        return jsonify({"error": "type and id required"}), 400

    # Which device type is required for this playback variant?
    required_type = TROLLEY_DEVICE_TYPE if playback_type == "trolley-timeline" else PLAYBACK_DEVICE_TYPE

    devices = []
    wrong_type = []
    missing = []
    for did in device_ids:
        d = device_store.get(did)
        if not d:
            missing.append(did)
            continue
        if d.get("type", "vents") != required_type:
            wrong_type.append({"id": did, "name": d.get("name"), "type": d.get("type")})
            continue
        devices.append(d)
    if wrong_type:
        return jsonify({
            "error": f"{playback_type} playback requires {required_type} devices",
            "unsupported_devices": wrong_type,
        }), 400
    if not devices:
        # Surface what was sent vs what the store sees so the UI can tell
        # the user to re-add a stale device (common after a data-dir reset
        # on a fresh PC where the Zustand cache outlives the backend).
        known_ids = [d["id"] for d in device_store.list_all()]
        return jsonify({
            "error": "No valid devices specified",
            "sent_ids": list(device_ids),
            "missing_ids": missing,
            "known_ids": known_ids,
        }), 400

    # Apply current settings
    settings = read_settings()
    _engine.tick_rate = settings.get("osc_frequency", 30)

    if playback_type == "timeline":
        timeline = timeline_store.get(playback_id)
        if not timeline:
            return jsonify({"error": "Timeline not found"}), 404
        _engine.start_timeline(timeline, devices)
        return jsonify({"ok": True, "message": "Timeline playback started"})

    elif playback_type == "trolley-timeline":
        timeline = trolley_timeline_store.get(playback_id)
        if not timeline:
            return jsonify({"error": "Trolley timeline not found"}), 404
        # Refuse to drive an uncalibrated trolley — /trolley/position would be
        # rejected by the firmware anyway, but a clear UI error is friendlier
        # than silent no-ops.
        receiver = OscReceiver(port=9001)
        uncalibrated = []
        for d in devices:
            ip = d.get("ip_address")
            if not ip:
                continue
            status = receiver.get_trolley_status(ip)
            if not status.get("calibrated"):
                uncalibrated.append({"id": d.get("id"), "name": d.get("name"), "ip": ip})
        if uncalibrated:
            return jsonify({
                "error": "Some trolleys are not calibrated. Run Home → Calibrate first.",
                "uncalibrated_devices": uncalibrated,
            }), 400
        _engine.start_trolley_timeline(timeline, devices)
        return jsonify({"ok": True, "message": "Trolley timeline playback started"})

    elif playback_type == "orchestration":
        orch = orchestration_store.get(playback_id)
        if not orch:
            return jsonify({"error": "Orchestration not found"}), 404

        # Resolve all timelines referenced in steps
        resolved_timelines = {}
        all_devices = device_store.list_all()
        devices_map = {d["id"]: d for d in all_devices}

        # Any trolley referenced in the steps is a hard error
        orch_wrong_type = []
        for step in orch.get("steps", []):
            for did in step.get("device_ids", []):
                d = devices_map.get(did)
                if d and d.get("type", "vents") != PLAYBACK_DEVICE_TYPE:
                    orch_wrong_type.append({"id": did, "name": d.get("name"), "type": d.get("type")})
        if orch_wrong_type:
            return jsonify({
                "error": f"Orchestration references non-{PLAYBACK_DEVICE_TYPE} devices",
                "unsupported_devices": orch_wrong_type,
            }), 400

        for step in orch.get("steps", []):
            tl_id = step.get("timeline_id")
            if tl_id and tl_id not in resolved_timelines:
                tl = timeline_store.get(tl_id)
                if tl:
                    resolved_timelines[tl_id] = tl

        _engine.start_orchestration(orch, resolved_timelines, devices_map)
        return jsonify({"ok": True, "message": "Orchestration playback started"})

    return jsonify({"error": "Invalid type (use 'timeline', 'trolley-timeline', or 'orchestration')"}), 400


@bp.route("/pause", methods=["POST"])
def pause_playback():
    _engine.pause()
    return jsonify({"ok": True})


@bp.route("/resume", methods=["POST"])
def resume_playback():
    _engine.resume()
    return jsonify({"ok": True})


@bp.route("/seek", methods=["POST"])
def seek_playback():
    data = request.get_json() or {}
    elapsed = data.get("elapsed")
    if elapsed is None:
        return jsonify({"error": "elapsed required"}), 400
    _engine.seek(float(elapsed))
    return jsonify({"ok": True})


@bp.route("/stop", methods=["POST"])
def stop_playback():
    _engine.stop()
    return jsonify({"ok": True, "message": "Playback stopped"})


@bp.route("/status", methods=["GET"])
def playback_status():
    return jsonify(_engine.status())
