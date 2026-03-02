"""Orchestration API routes."""

from flask import Blueprint, request, jsonify
from storage.json_store import JsonStore
from config import DATA_DIR

bp = Blueprint("orchestrations", __name__)
store = JsonStore(DATA_DIR, "orchestrations", "orch")


def _new_orchestration(data: dict) -> dict:
    orch = {
        "name": data.get("name", "Untitled"),
        "loop": data.get("loop", False),
        "steps": data.get("steps", []),
    }
    if "id" in data:
        orch["id"] = data["id"]
    return orch


@bp.route("", methods=["GET"])
def list_orchestrations():
    return jsonify(store.list_all())


@bp.route("", methods=["POST"])
def create_orchestration():
    data = request.get_json() or {}
    return jsonify(store.create(_new_orchestration(data))), 201


@bp.route("/<orch_id>", methods=["GET"])
def get_orchestration(orch_id):
    orch = store.get(orch_id)
    if not orch:
        return jsonify({"error": "Not found"}), 404
    return jsonify(orch)


@bp.route("/<orch_id>", methods=["PUT"])
def update_orchestration(orch_id):
    data = request.get_json() or {}
    updated = store.update(orch_id, data)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    return jsonify(updated)


@bp.route("/<orch_id>", methods=["DELETE"])
def delete_orchestration(orch_id):
    if store.delete(orch_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404
