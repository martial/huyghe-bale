"""Resolve the latest commit on `main` for the admin's "update available" pill.

Resolution order (first non-None wins):
  1. Local git checkout — dev mode (`python app.py` from the repo).
  2. GitHub public API — bundled .app on a host with internet.
  3. Embedded VERSION file baked in at build time — offline kiosk fallback.
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.request

logger = logging.getLogger("version_checker")

_cache = {"data": None, "ts": 0}
CACHE_TTL = 60

_GITHUB_REPO = "martial/huyghe-bale"
_GITHUB_BRANCH = "main"
_GITHUB_TIMEOUT = 5

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
    except Exception as e:
        logger.debug("Embedded VERSION read failed: %s", e)
        return None


def _git_root():
    """Find the git repo root from this file's location, or None if we're
    not inside a git checkout (e.g. running from inside _MEIPASS)."""
    cwd = os.path.dirname(os.path.abspath(__file__))
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _fetch_from_local_git():
    """Fetch + read origin/main from a local git checkout."""
    root = _git_root()
    if not root:
        return None
    try:
        subprocess.check_output(["git", "fetch", "origin", _GITHUB_BRANCH],
                                cwd=root, text=True, timeout=10,
                                stderr=subprocess.DEVNULL)
        h = subprocess.check_output(
            ["git", "rev-parse", "--short", f"origin/{_GITHUB_BRANCH}"],
            cwd=root, text=True,
        ).strip()
        log = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci\n%s", f"origin/{_GITHUB_BRANCH}"],
            cwd=root, text=True,
        ).strip().split("\n", 1)
        return {"hash": h, "date": log[0], "message": log[1] if len(log) > 1 else ""}
    except Exception as e:
        logger.debug("Local git fetch failed: %s", e)
        return None


def _fetch_from_github():
    """Hit GitHub's public API for the latest commit on the configured branch."""
    url = f"https://api.github.com/repos/{_GITHUB_REPO}/commits/{_GITHUB_BRANCH}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "huyghe-bale-admin",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=_GITHUB_TIMEOUT) as resp:
            data = json.load(resp)
        return {
            "hash": data["sha"][:7],
            "date": data["commit"]["committer"]["date"],
            "message": data["commit"]["message"].split("\n", 1)[0],
        }
    except Exception as e:
        logger.debug("GitHub API fetch failed: %s", e)
        return None


def get_latest_version():
    """Return latest commit on main, cached for 60s. See module docstring."""
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    for fetcher in (_fetch_from_local_git, _fetch_from_github, _read_embedded_version):
        result = fetcher()
        if result:
            _cache["data"] = result
            _cache["ts"] = now
            return result

    return {"hash": "unknown", "date": "unknown", "message": ""}
