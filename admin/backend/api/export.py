"""Export/Import API routes."""

import json
from flask import Blueprint, request, jsonify, Response
from storage.json_store import JsonStore
from engine.interpolation import evaluate_lane
from api.settings import _read as read_settings
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


@bp.route("/timeline/<timeline_id>/sampled", methods=["GET"])
def export_timeline_sampled(timeline_id):
    """Frame-by-frame rendered values at a chosen FPS. One sample per frame including t=0 and t=duration."""
    tl = timeline_store.get(timeline_id)
    if not tl:
        return jsonify({"error": "Not found"}), 404

    default_fps = int(read_settings().get("osc_frequency", 30))
    try:
        fps = int(request.args.get("fps", default_fps))
    except ValueError:
        return jsonify({"error": "fps must be an integer"}), 400
    if not 1 <= fps <= 1000:
        return jsonify({"error": "fps must be between 1 and 1000"}), 400

    duration = float(tl.get("duration", 0))
    lanes = tl.get("lanes", {}) or {}
    lane_keys = sorted(lanes.keys())

    frame_count = int(round(duration * fps)) + 1
    samples = []
    for i in range(frame_count):
        t_s = i / fps
        if t_s > duration:
            t_s = duration
        sample = {"t_ms": round(t_s * 1000)}
        for key in lane_keys:
            points = lanes[key].get("points", []) or []
            sample[key] = round(evaluate_lane(sorted(points, key=lambda p: p["time"]), t_s), 6)
        samples.append(sample)

    payload = {
        "id": tl.get("id"),
        "name": tl.get("name"),
        "duration": duration,
        "fps": fps,
        "frame_count": frame_count,
        "lanes": lane_keys,
        "samples": samples,
    }
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={timeline_id}_sampled_{fps}fps.json"},
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


@bp.route("/orchestration/<orch_id>/sampled", methods=["GET"])
def export_orchestration_sampled(orch_id):
    """Frame-by-frame rendered values for an orchestration. During delay_before, lanes hold the last emitted value."""
    orch = orchestration_store.get(orch_id)
    if not orch:
        return jsonify({"error": "Not found"}), 404

    default_fps = int(read_settings().get("osc_frequency", 30))
    try:
        fps = int(request.args.get("fps", default_fps))
    except ValueError:
        return jsonify({"error": "fps must be an integer"}), 400
    if not 1 <= fps <= 1000:
        return jsonify({"error": "fps must be between 1 and 1000"}), 400

    steps = orch.get("steps", []) or []
    resolved = {}
    lane_keys_set = set()
    for step in steps:
        tl_id = step.get("timeline_id")
        if tl_id and tl_id not in resolved:
            tl = timeline_store.get(tl_id)
            if tl:
                resolved[tl_id] = tl
                lane_keys_set.update((tl.get("lanes") or {}).keys())
    lane_keys = sorted(lane_keys_set)

    segments = []  # flat list of {kind: "delay"|"play", duration, step_idx, step_label, tl_id}
    for idx, step in enumerate(steps):
        label = step.get("label", f"Step {idx + 1}")
        delay = float(step.get("delay_before", 0.0) or 0.0)
        if delay > 0:
            segments.append({"kind": "delay", "duration": delay, "step_idx": idx, "step_label": label, "tl_id": None})
        tl_id = step.get("timeline_id")
        tl = resolved.get(tl_id) if tl_id else None
        if tl is not None:
            segments.append({
                "kind": "play",
                "duration": float(tl.get("duration", 0.0) or 0.0),
                "step_idx": idx,
                "step_label": label,
                "tl_id": tl_id,
            })

    total_duration = sum(s["duration"] for s in segments)
    frame_count = int(round(total_duration * fps)) + 1 if total_duration > 0 else 0

    # Pre-sort points per lane per timeline
    sorted_points = {
        tl_id: {k: sorted(((tl.get("lanes") or {}).get(k) or {}).get("points", []) or [], key=lambda p: p["time"])
                for k in lane_keys}
        for tl_id, tl in resolved.items()
    }

    held = {k: 0.0 for k in lane_keys}
    samples = []
    seg_i = 0
    seg_elapsed = 0.0  # time already consumed within the current segment group
    cumulative_until_seg = 0.0  # total time before segments[seg_i]

    for i in range(frame_count):
        t_s = i / fps
        if t_s > total_duration:
            t_s = total_duration
        # Advance segment cursor
        while seg_i < len(segments) and t_s >= cumulative_until_seg + segments[seg_i]["duration"]:
            # Leaving this segment — if it was a "play", update held to final values
            seg = segments[seg_i]
            if seg["kind"] == "play":
                for k in lane_keys:
                    held[k] = round(evaluate_lane(sorted_points[seg["tl_id"]][k], seg["duration"]), 6)
            cumulative_until_seg += seg["duration"]
            seg_i += 1

        if seg_i >= len(segments):
            step_idx = segments[-1]["step_idx"] if segments else -1
            step_label = segments[-1]["step_label"] if segments else ""
            kind = "end"
            sample_vals = dict(held)
        else:
            seg = segments[seg_i]
            step_idx = seg["step_idx"]
            step_label = seg["step_label"]
            kind = seg["kind"]
            if kind == "delay":
                sample_vals = dict(held)
            else:
                local_t = t_s - cumulative_until_seg
                sample_vals = {
                    k: round(evaluate_lane(sorted_points[seg["tl_id"]][k], local_t), 6)
                    for k in lane_keys
                }

        sample = {"t_ms": round(t_s * 1000), "step": step_idx, "step_label": step_label, "phase": kind}
        sample.update(sample_vals)
        samples.append(sample)

    payload = {
        "id": orch.get("id"),
        "name": orch.get("name"),
        "loop": bool(orch.get("loop", False)),
        "total_duration": total_duration,
        "fps": fps,
        "frame_count": frame_count,
        "lanes": lane_keys,
        "samples": samples,
    }
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={orch_id}_sampled.json"},
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
