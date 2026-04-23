"""Bundled app entry point — pywebview + Flask.

Installation-ready hardening:
  * file-backed rotating log under the platform data dir so on-site crew
    has something to send to a developer;
  * Flask is supervised: a bind error or later crash surfaces as a native
    error window rather than an indefinitely-blank WKWebView;
  * readiness probe hits /api/v1/health (not just /) so we know the app
    is up, not just the socket.
"""

import logging
import os
import sys
import threading
import time
import urllib.request
from logging.handlers import RotatingFileHandler

import webview

# Detect PyInstaller frozen environment
_MEIPASS = getattr(sys, "_MEIPASS", None)

if _MEIPASS:
    dist_dir = os.path.join(_MEIPASS, "frontend", "dist")
    if sys.platform == "win32":
        app_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "PierreHuygheBale",
        )
    else:
        app_dir = os.path.expanduser(
            "~/Library/Application Support/PierreHuygheBale"
        )
    data_dir = os.path.join(app_dir, "data")
    log_dir = os.path.join(app_dir, "logs")
    for sub in ("timelines", "devices", "orchestrations", "trolley_timelines"):
        os.makedirs(os.path.join(data_dir, sub), exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "backend.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root_logger.addHandler(handler)
    # Log where we're reading + writing persistent state so the operator
    # can confirm it's surviving across rebuilds (it should — APPDATA is
    # outside the bundle).
    logging.getLogger("launcher").info(
        "Bundled app paths — data_dir=%s log_dir=%s", data_dir, log_dir,
    )
else:
    dist_dir = None
    data_dir = None
    log_path = None

logger = logging.getLogger("launcher")

# CRITICAL: override config.DATA_DIR BEFORE any `from api import …` runs.
# Any api module (and their transitive imports like api.devices, which
# api.health pulls at top level) captures DATA_DIR via `from config
# import DATA_DIR` at module-load time. If that capture happens before
# this override, the module's JsonStore ends up pointing at the bundle's
# default `_internal/data` folder — which gets replaced on every rebuild,
# so every new build looks like "all devices got wiped".
if data_dir is not None:
    import config  # noqa: E402
    config.DATA_DIR = data_dir

from app import create_app  # noqa: E402 — must import after path setup

# Surface the resolved log path to the health endpoint so the UI / docs
# can tell the operator where to look. Safe to do now — the override
# above propagated to api.devices / api.health at their first import.
try:
    import api.health as _health_mod  # noqa: E402
    _health_mod.LOG_PATH = log_path
except Exception:  # pragma: no cover — defensive during startup
    pass

app = create_app(dist_dir=dist_dir, data_dir=data_dir)

flask_error: str | None = None


def _run_flask():
    global flask_error
    try:
        app.run(host="127.0.0.1", port=5001, use_reloader=False)
    except Exception as e:
        flask_error = str(e)
        logger.exception("Flask server crashed")


# Start Flask in a daemon thread
server = threading.Thread(target=_run_flask, daemon=True, name="flask")
server.start()

# Wait up to 5 s for the app to answer /api/v1/health (proves Flask is up
# AND the API blueprints are registered — not just that the socket is listening).
flask_ready = False
for _ in range(50):
    if flask_error:
        break
    try:
        urllib.request.urlopen("http://127.0.0.1:5001/api/v1/health", timeout=0.25)
        flask_ready = True
        break
    except Exception:
        time.sleep(0.1)


class Api:
    """JS bridge — WKWebView ignores <a download> and Content-Disposition,
    so the frontend calls save_file() to pop a native Save As dialog."""

    def save_file(self, filename, content):
        win = webview.windows[0]
        path = win.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=filename
        )
        if not path:
            return False
        # create_file_dialog returns str on some platforms, tuple on others
        if isinstance(path, (list, tuple)):
            path = path[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True


def _error_html(title: str, detail: str) -> str:
    log_note = (
        f"<p>Full log: <code>{log_path}</code></p>" if log_path else ""
    )
    return f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif;
         background:#1a1a1a; color:#e5e5e5; padding:40px; line-height:1.6; }}
  h1 {{ color:#f87171; font-weight:500; }}
  code {{ background:#2a2a2a; padding:2px 6px; border-radius:4px; font-size:.9em; }}
  pre {{ background:#2a2a2a; padding:12px; border-radius:6px; overflow:auto; }}
  .hint {{ color:#a1a1aa; font-size:.9em; margin-top:24px; }}
</style></head><body>
  <h1>PIERRE HUYGHE BALE — startup error</h1>
  <p>{title}</p>
  <pre>{detail}</pre>
  {log_note}
  <p class="hint">
    Common cause: another copy of the app is already running, or another service
    is holding port <code>5001</code>. Quit it and relaunch.
  </p>
</body></html>
"""


if not flask_ready:
    title = "The backend failed to start."
    detail = flask_error or "No response from http://127.0.0.1:5001/api/v1/health"
    logger.error("Startup failed: %s", detail)
    webview.create_window(
        "PIERRE HUYGHE BALE — Error",
        html=_error_html(title, detail),
        width=720,
        height=480,
    )
else:
    webview.create_window(
        "PIERRE HUYGHE BALE",
        "http://127.0.0.1:5001",
        width=1280,
        height=800,
        js_api=Api(),
    )

# debug=True exposes the WebView2 / WKWebView DevTools (right-click →
# "Inspect element") so on-site diagnostics don't require a source checkout.
webview.start(debug=True)
