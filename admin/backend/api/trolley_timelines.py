"""Trolley timeline API — event-based playback.

Each timeline is a sorted list of bangs (discrete OSC events at specific
times). Playback fires the corresponding /trolley/* address per event;
smooth motion between events is handled on the Pi (the follow loop for
position, the step-burst loop for step, etc.).

Event schema:
    {"id": "ev_xxx", "time": seconds, "command": str, "value"?: num}

    command       | value            | OSC address         | notes
    ------------- | ---------------- | ------------------- | -------------------
    enable        | 0 | 1            | /trolley/enable     | engage/release driver
    dir           | 0 | 1            | /trolley/dir        | 0 = reverse, 1 = forward
    speed         | float 0..1       | /trolley/speed      | pulse frequency
    step          | int N            | /trolley/step       | burst N pulses
    stop          | —                | /trolley/stop       | abort current motion
    home          | —                | /trolley/home       | reverse until limit switch
    position      | float 0..1       | /trolley/position   | follow to target

Legacy `lane.points` schemas (continuous position curves) are translated
to `position` events on load. No writable lane field remains.
"""

from flask import Blueprint, request, jsonify

from storage.json_store import JsonStore
from config import DATA_DIR

bp = Blueprint("trolley_timelines", __name__)
store = JsonStore(DATA_DIR, "trolley_timelines", "trtl")

_engine = None

VALID_COMMANDS = ("enable", "dir", "speed", "step", "stop", "home", "position")
COMMANDS_WITH_VALUE = {"enable", "dir", "speed", "step", "position"}


def set_engine(engine):
    global _engine
    _engine = engine


def _migrate_legacy(tl: dict) -> dict:
    """Old trolley timelines used `lane.points` (continuous position curve).
    Translate each point into a `position` event so the playback engine only
    needs the event code path. Non-destructive: returns a new dict, callers
    should write back if they want persistence."""
    if "events" in tl and isinstance(tl["events"], list):
        return tl
    lane = tl.get("lane") or {}
    points = lane.get("points") or []
    events = []
    for i, p in enumerate(sorted(points, key=lambda x: x.get("time", 0))):
        events.append({
            "id": p.get("id") or f"ev_legacy_{i}",
            "time": float(p.get("time", 0)),
            "command": "position",
            "value": float(p.get("value", 0)),
        })
    out = dict(tl)
    out["events"] = events
    out.pop("lane", None)
    return out


def _normalize_event(ev: dict) -> dict:
    """Coerce types and drop fields we don't store. Raises ValueError on bad input."""
    cmd = ev.get("command")
    if cmd not in VALID_COMMANDS:
        raise ValueError(f"unknown command: {cmd!r}")
    out = {
        "id": ev.get("id") or "",
        "time": max(0.0, float(ev.get("time", 0))),
        "command": cmd,
    }
    if cmd in COMMANDS_WITH_VALUE:
        if "value" not in ev or ev["value"] is None:
            raise ValueError(f"command {cmd!r} requires a value")
        out["value"] = float(ev["value"])
    return out


def _normalize_events(events):
    if not isinstance(events, list):
        return []
    normalized = []
    for ev in events:
        try:
            normalized.append(_normalize_event(ev))
        except (ValueError, TypeError):
            continue
    normalized.sort(key=lambda e: e["time"])
    return normalized


def _summary(tl: dict) -> dict:
    tl = _migrate_legacy(tl)
    return {
        "id": tl["id"],
        "name": tl.get("name", ""),
        "duration": tl.get("duration", 0),
        "events": len(tl.get("events", [])),
        "created_at": tl.get("created_at"),
    }


def _new(data: dict) -> dict:
    tl = {
        "name": data.get("name", "Untitled"),
        "duration": data.get("duration", 60.0),
        "events": _normalize_events(data.get("events", [])),
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
    return jsonify(_migrate_legacy(tl))


@bp.route("", methods=["POST"])
def create():
    data = request.get_json() or {}
    return jsonify(store.create(_new(data))), 201


@bp.route("/<tl_id>", methods=["PUT"])
def update(tl_id):
    data = request.get_json() or {}
    # Clients always send `events` now; strip legacy `lane` if any.
    payload = dict(data)
    payload.pop("lane", None)
    if "events" in payload:
        payload["events"] = _normalize_events(payload["events"])
    updated = store.update(tl_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    if _engine is not None and hasattr(_engine, "reload_timeline"):
        try:
            _engine.reload_timeline(_migrate_legacy(updated))
        except Exception:
            pass
    return jsonify(_migrate_legacy(updated))


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
    copy = _migrate_legacy(dict(original))
    del copy["id"]
    copy["name"] = f"{copy.get('name', '')} (copy)"
    return jsonify(store.create(copy)), 201
