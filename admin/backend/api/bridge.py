"""Bridge API — live feed + state + controls for the OSC bridge.

Routes:
  GET  /api/v1/bridge/state   → {enabled, running, port, routing, error, events}
  GET  /api/v1/bridge/stream  → SSE: one JSON event per dispatched OSC message
  POST /api/v1/bridge/clear   → wipe the ring buffer
"""

import json
import queue
import time

from flask import Blueprint, Response, jsonify

from api.settings import _read as read_settings

bp = Blueprint("bridge", __name__)

_bridge = None


def set_bridge(bridge):
    """Register the shared OscBridge instance (called from app.py on boot)."""
    global _bridge
    _bridge = bridge


def _state_payload():
    settings = read_settings()
    if _bridge is None:
        return {
            "enabled": bool(settings.get("bridge_enabled")),
            "running": False,
            "port": settings.get("bridge_port"),
            "routing": settings.get("bridge_routing"),
            "error": "bridge not initialised",
            "events": [],
        }
    return {
        "enabled": bool(settings.get("bridge_enabled")),
        "running": _bridge.running,
        "port": _bridge.port,
        "routing": _bridge.routing,
        "error": _bridge.error,
        "events": _bridge.get_events(),
    }


@bp.route("/state", methods=["GET"])
def get_state():
    return jsonify(_state_payload())


@bp.route("/clear", methods=["POST"])
def clear_events():
    if _bridge is not None:
        _bridge.clear_events()
    return jsonify({"ok": True})


@bp.route("/stream", methods=["GET"])
def stream():
    """SSE feed of bridge events.

    Emits the current ring buffer on connect, then one frame per incoming
    OSC message as it arrives. Heartbeat every 15 s so proxies don't time
    out the connection.
    """
    def generate():
        if _bridge is None:
            yield f"data: {json.dumps({'error': 'bridge not initialised'})}\n\n"
            return
        # Replay the buffer first so late subscribers have context.
        for ev in _bridge.get_events():
            yield f"data: {json.dumps(ev)}\n\n"
        q = _bridge.subscribe()
        try:
            last_beat = time.time()
            while True:
                try:
                    ev = q.get(timeout=5.0)
                    yield f"data: {json.dumps(ev)}\n\n"
                except queue.Empty:
                    pass
                if time.time() - last_beat > 15:
                    # SSE comment line doubles as a keep-alive
                    yield ": heartbeat\n\n"
                    last_beat = time.time()
        finally:
            _bridge.unsubscribe(q)

    return Response(generate(), mimetype="text/event-stream")
