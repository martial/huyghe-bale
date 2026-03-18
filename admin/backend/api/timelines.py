"""Timeline API routes."""

from flask import Blueprint, request, jsonify
from storage.json_store import JsonStore
from config import DATA_DIR

bp = Blueprint("timelines", __name__)
store = JsonStore(DATA_DIR, "timelines", "tl")


def _summary(tl: dict) -> dict:
    """Return a summary view (no full lane data)."""
    return {
        "id": tl["id"],
        "name": tl.get("name", ""),
        "duration": tl.get("duration", 0),
        "lane_a_points": len(tl.get("lanes", {}).get("a", {}).get("points", [])),
        "lane_b_points": len(tl.get("lanes", {}).get("b", {}).get("points", [])),
        "created_at": tl.get("created_at"),
    }


def _new_timeline(data: dict) -> dict:
    """Ensure a timeline has required structure."""
    tl = {
        "name": data.get("name", "Untitled"),
        "duration": data.get("duration", 60.0),
        "lanes": data.get("lanes", {
            "a": {"label": "Variable A (EnA)", "points": []},
            "b": {"label": "Variable B (EnB)", "points": []},
        }),
    }
    if "id" in data:
        tl["id"] = data["id"]
    return tl


@bp.route("", methods=["GET"])
def list_timelines():
    return jsonify([_summary(tl) for tl in store.list_all()])


@bp.route("/<timeline_id>", methods=["GET"])
def get_timeline(timeline_id):
    tl = store.get(timeline_id)
    if not tl:
        return jsonify({"error": "Not found"}), 404
    return jsonify(tl)


@bp.route("", methods=["POST"])
def create_timeline():
    data = request.get_json() or {}
    tl = _new_timeline(data)
    created = store.create(tl)
    return jsonify(created), 201


@bp.route("/<timeline_id>", methods=["PUT"])
def update_timeline(timeline_id):
    data = request.get_json() or {}
    updated = store.update(timeline_id, data)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    return jsonify(updated)


@bp.route("/<timeline_id>", methods=["DELETE"])
def delete_timeline(timeline_id):
    if store.delete(timeline_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@bp.route("/<timeline_id>/duplicate", methods=["POST"])
def duplicate_timeline(timeline_id):
    original = store.get(timeline_id)
    if not original:
        return jsonify({"error": "Not found"}), 404
    copy = dict(original)
    del copy["id"]
    copy["name"] = f"{copy.get('name', '')} (copy)"
    created = store.create(copy)
    return jsonify(created), 201
