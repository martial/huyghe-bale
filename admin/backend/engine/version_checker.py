"""Check latest version from GitHub remote or local git."""

import json
import os
import subprocess
import time
import urllib.request

_cache = {"data": None, "ts": 0}
CACHE_TTL = 60


def invalidate_cache():
    """Clear the version cache so next call fetches fresh data."""
    _cache["data"] = None
    _cache["ts"] = 0


def _git_root():
    """Find the git repo root from this file's location."""
    cwd = os.path.dirname(os.path.abspath(__file__))
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True
        ).strip()
    except Exception:
        return cwd


def _detect_github_repo():
    """Parse owner/repo from git remote origin URL."""
    try:
        root = _git_root()
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=root, text=True
        ).strip()
        # Handle SSH: git@github.com:owner/repo.git
        if url.startswith("git@"):
            path = url.split(":", 1)[1]
        # Handle HTTPS: https://github.com/owner/repo.git
        elif "github.com" in url:
            path = url.split("github.com/", 1)[1]
        else:
            return None
        path = path.removesuffix(".git")
        parts = path.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    except Exception:
        pass
    return None


def _fetch_from_github(repo):
    """Try GitHub API (works for public repos)."""
    url = f"https://api.github.com/repos/{repo}/commits/main"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        return {
            "hash": data["sha"][:7],
            "date": data["commit"]["committer"]["date"],
            "message": data["commit"]["message"].split("\n")[0],
        }


def _fetch_from_local_git():
    """Fetch + read origin/main from local git (works for private repos)."""
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
    """Return latest commit on main. Tries GitHub API first, falls back to local git. Cached for 60s."""
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    # Try GitHub API (fast, no auth needed for public repos)
    repo = _detect_github_repo()
    if repo:
        try:
            result = _fetch_from_github(repo)
            _cache["data"] = result
            _cache["ts"] = now
            return result
        except Exception:
            pass

    # Fallback: git fetch + read origin/main locally
    try:
        result = _fetch_from_local_git()
        _cache["data"] = result
        _cache["ts"] = now
        return result
    except Exception:
        return {"hash": "unknown", "date": "unknown", "message": ""}
