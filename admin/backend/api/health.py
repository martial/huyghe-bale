"""Health API — a single endpoint the frontend polls to surface
subsystem liveness (OSC receiver, bridge, playback thread).

The launcher sets `LOG_PATH` at startup so the UI can tell the operator
where to find crash logs."""

import logging

from flask import Blueprint, jsonify

import config
from api.devices import store as device_store
from engine.osc_receiver import OscReceiver

logger = logging.getLogger(__name__)

bp = Blueprint("health", __name__)

# Populated by launcher.py when running as a bundled app; stays None
# during `python app.py` dev runs (logs go to stdout in that case).
LOG_PATH: "str | None" = None


@bp.route("", methods=["GET"])
def get_health():
    receiver = OscReceiver(port=9001)

    # Bridge and playback state are optional — pull them without taking
    # hard imports at module load so circular-import risk stays low.
    bridge_state = {"running": False, "port": None, "error": None}
    try:
        from api.bridge import _bridge
        if _bridge is not None:
            bridge_state = {
                "running": _bridge.running,
                "port": _bridge.port,
                "error": _bridge.error,
            }
    except Exception as e:
        bridge_state["error"] = f"bridge introspection failed: {e}"

    playback_state = {"thread_alive": False, "playing": False, "last_error": None}
    try:
        from api.playback import _engine
        if _engine is not None:
            playback_state = {
                "thread_alive": _engine.thread_alive,
                "playing": _engine.playing,
                "last_error": _engine.last_error,
            }
    except Exception as e:
        playback_state["last_error"] = f"playback introspection failed: {e}"

    vents_over_temp = []
    vents_probe_unassigned = []
    try:
        for dev in device_store.list_all():
            if dev.get("type") != "vents":
                continue
            ip = dev.get("ip_address")
            if not ip:
                continue
            snap = receiver.get_vents_status(ip)
            if snap.get("state") == "over_temp":
                vents_over_temp.append(
                    {
                        "device_id": dev.get("id"),
                        "name": dev.get("name") or dev.get("id"),
                        "temp1_c": snap.get("temp1_c"),
                        "temp2_c": snap.get("temp2_c"),
                        "target_c": snap.get("target_c"),
                        "max_temp_c": snap.get("max_temp_c"),
                        "temp_hot_c": snap.get("temp_hot_c"),
                        "temp_cold_c": snap.get("temp_cold_c"),
                        "hot_target_c": snap.get("hot_target_c"),
                        "cold_target_c": snap.get("cold_target_c"),
                    }
                )
            if snap.get("state") == "probe_unassigned":
                vents_probe_unassigned.append(
                    {
                        "device_id": dev.get("id"),
                        "name": dev.get("name") or dev.get("id"),
                        "probe_hot_id": snap.get("probe_hot_id"),
                        "probe_cold_id": snap.get("probe_cold_id"),
                        "discovered": [p.get("id") for p in (snap.get("probes") or [])],
                    }
                )
    except Exception as e:
        logger.warning("vents health aggregation failed: %s", e)

    payload = {
        "osc_receiver": {
            "running": receiver.running,
            "port": receiver.port,
            "error": receiver.error,
        },
        "bridge": bridge_state,
        "playback": playback_state,
        "vents_over_temp": vents_over_temp,
        "vents_probe_unassigned": vents_probe_unassigned,
        "log_path": LOG_PATH,
        # Read live from config so a late-override is reflected, not the
        # value captured at module-import time.
        "data_dir": config.DATA_DIR,
        "device_count": len(device_store.list_all()),
    }
    payload["ok"] = (
        payload["osc_receiver"]["error"] is None
        and payload["bridge"]["error"] is None
        and payload["playback"]["last_error"] is None
    )
    return jsonify(payload)
