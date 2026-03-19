"""Check latest version from GitHub remote, local git, or embedded VERSION file."""

import json
import os
import subprocess
import sys
import time

_cache = {"data": None, "ts": 0}
CACHE_TTL = 60

# Path to the VERSION file embedded at build time
_MEIPASS = getattr(sys, "_MEIPASS", None)
_VERSION_FILE = os.path.join(_MEIPASS, "VERSION") if _MEIPASS else None


def invalidate_cache():
    """Clear the version cache so next call fetches fresh data."""
    _cache["data"] = None
    _cache["ts"] = 0


def _read_embedded_version():
    """Read the VERSION file bundled inside the packaged app."""
    if not _VERSION_FILE or not os.path.exists(_VERSION_FILE):
        return None
    try:
        with open(_VERSION_FILE) as f:
            data = json.load(f)
        return {
            "hash": data.get("hash", "unknown"),
            "date": data.get("date", "unknown"),
            "message": data.get("message", ""),
        }
    except Exception:
        return None


def _git_root():
    """Find the git repo root from this file's location."""
    cwd = os.path.dirname(os.path.abspath(__file__))
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
        ).strip()
    except Exception:
        return cwd


def _fetch_from_local_git():
    """Fetch + read origin/main from local git."""
    root = _git_root()
    subprocess.check_output(["git", "fetch", "origin", "main"], cwd=root, text=True, timeout=10)
    h = subprocess.check_output(
        ["git", "rev-parse", "--short", "origin/main"], cwd=root, text=True
    ).strip()
    log = subprocess.check_output(
        ["git", "log", "-1", "--format=%ci\n%s", "origin/main"], cwd=root, text=True
    ).strip().split("\n", 1)
    return {"hash": h, "date": log[0], "message": log[1] if len(log) > 1 else ""}


def get_latest_version():
    """Return latest commit on main. Uses embedded VERSION in packaged app, local git in dev. Cached for 60s."""
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    # Packaged app: use embedded VERSION file
    embedded = _read_embedded_version()
    if embedded:
        _cache["data"] = embedded
        _cache["ts"] = now
        return embedded

    # Dev mode: git fetch + read origin/main locally
    try:
        result = _fetch_from_local_git()
        _cache["data"] = result
        _cache["ts"] = now
        return result
    except Exception:
        return {"hash": "unknown", "date": "unknown", "message": ""}
