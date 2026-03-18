"""Health API routes."""

from flask import Blueprint, jsonify

from engine.osc_receiver import OscReceiver

bp = Blueprint("health", __name__)


@bp.route("", methods=["GET"])
def get_health():
    receiver = OscReceiver(port=9001)
    return jsonify({
        "osc_receiver": {
            "running": receiver.running,
            "port": receiver.port,
            "error": receiver.error,
        }
    })
