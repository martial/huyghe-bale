"""Export/Import API routes."""

import json
from flask import Blueprint, request, jsonify, Response
from storage.json_store import JsonStore
from config import DATA_DIR

bp = Blueprint("export", __name__)

timeline_store = JsonStore(DATA_DIR, "timelines", "tl")
orchestration_store = JsonStore(DATA_DIR, "orchestrations", "orch")


@bp.route("/timeline/<timeline_id>", methods=["GET"])
def export_timeline(timeline_id):
    tl = timeline_store.get(timeline_id)
    if not tl:
        return jsonify({"error": "Not found"}), 404
    return Response(
        json.dumps(tl, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={timeline_id}.json"},
    )


@bp.route("/orchestration/<orch_id>", methods=["GET"])
def export_orchestration(orch_id):
    orch = orchestration_store.get(orch_id)
    if not orch:
        return jsonify({"error": "Not found"}), 404

    # Embed resolved timelines
    embedded = dict(orch)
    embedded["_embedded_timelines"] = {}
    for step in orch.get("steps", []):
        tl_id = step.get("timeline_id")
        if tl_id:
            tl = timeline_store.get(tl_id)
            if tl:
                embedded["_embedded_timelines"][tl_id] = tl

    return Response(
        json.dumps(embedded, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={orch_id}.json"},
    )


@bp.route("/import/timeline", methods=["POST"])
def import_timeline():
    if "file" in request.files:
        file = request.files["file"]
        data = json.load(file)
    else:
        data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Strip existing ID so a new one is assigned
    data.pop("id", None)
    created = timeline_store.create(data)
    return jsonify(created), 201
