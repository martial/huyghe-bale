"""Trolley timeline API — single-lane position keyframes.

Parallel to api/timelines.py but persisted under data/trolley_timelines/ with
prefix 'trtl'. Schema has a single `lane` (label + points) instead of a/b lanes;
point values are position along the rail (0..1), not PWM duty.
"""

from flask import Blueprint, request, jsonify

from storage.json_store import JsonStore
from config import DATA_DIR

bp = Blueprint("trolley_timelines", __name__)
store = JsonStore(DATA_DIR, "trolley_timelines", "trtl")

_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


def _summary(tl: dict) -> dict:
    return {
        "id": tl["id"],
        "name": tl.get("name", ""),
        "duration": tl.get("duration", 0),
        "points": len((tl.get("lane") or {}).get("points", [])),
        "created_at": tl.get("created_at"),
    }


def _new(data: dict) -> dict:
    tl = {
        "name": data.get("name", "Untitled"),
        "duration": data.get("duration", 60.0),
        "lane": data.get("lane", {"label": "Position", "points": []}),
    }
    if "id" in data:
        tl["id"] = data["id"]
    return tl


@bp.route("", methods=["GET"])
def list_all():
    return jsonify([_summary(tl) for tl in store.list_all()])


@bp.route("/<tl_id>", methods=["GET"])
def get_one(tl_id):
    tl = store.get(tl_id)
    if not tl:
        return jsonify({"error": "Not found"}), 404
    return jsonify(tl)


@bp.route("", methods=["POST"])
def create():
    data = request.get_json() or {}
    return jsonify(store.create(_new(data))), 201


@bp.route("/<tl_id>", methods=["PUT"])
def update(tl_id):
    data = request.get_json() or {}
    updated = store.update(tl_id, data)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    if _engine is not None and hasattr(_engine, "reload_timeline"):
        try:
            _engine.reload_timeline(updated)
        except Exception:
            pass
    return jsonify(updated)


@bp.route("/<tl_id>", methods=["DELETE"])
def delete(tl_id):
    if store.delete(tl_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@bp.route("/<tl_id>/duplicate", methods=["POST"])
def duplicate(tl_id):
    original = store.get(tl_id)
    if not original:
        return jsonify({"error": "Not found"}), 404
    copy = dict(original)
    del copy["id"]
    copy["name"] = f"{copy.get('name', '')} (copy)"
    return jsonify(store.create(copy)), 201
