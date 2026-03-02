"""Settings API routes."""

import json
import os

from flask import Blueprint, jsonify, request

from config import DATA_DIR

bp = Blueprint("settings", __name__)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "osc_frequency": 30,  # Hz
}


def _read():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return {**DEFAULTS, **json.load(f)}
    return dict(DEFAULTS)


def _write(data):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


@bp.route("", methods=["GET"])
def get_settings():
    return jsonify(_read())


@bp.route("", methods=["PUT"])
def update_settings():
    body = request.get_json() or {}
    current = _read()
    if "osc_frequency" in body:
        val = body["osc_frequency"]
        if not isinstance(val, (int, float)) or val < 1 or val > 120:
            return jsonify({"error": "osc_frequency must be between 1 and 120 Hz"}), 400
        current["osc_frequency"] = int(val)
    _write(current)
    return jsonify(current)
