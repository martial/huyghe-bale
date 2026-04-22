"""Health API — a single endpoint the frontend polls to surface
subsystem liveness (OSC receiver, bridge, playback thread).

The launcher sets `LOG_PATH` at startup so the UI can tell the operator
where to find crash logs."""

from flask import Blueprint, jsonify

from engine.osc_receiver import OscReceiver

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

    payload = {
        "osc_receiver": {
            "running": receiver.running,
            "port": receiver.port,
            "error": receiver.error,
        },
        "bridge": bridge_state,
        "playback": playback_state,
        "log_path": LOG_PATH,
    }
    payload["ok"] = (
        payload["osc_receiver"]["error"] is None
        and payload["bridge"]["error"] is None
        and payload["playback"]["last_error"] is None
    )
    return jsonify(payload)
