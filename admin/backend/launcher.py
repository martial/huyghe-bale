"""Bundled app entry point — pywebview + Flask."""

import os
import sys
import threading
import time
import urllib.request

import webview

# Detect PyInstaller frozen environment
_MEIPASS = getattr(sys, "_MEIPASS", None)

if _MEIPASS:
    dist_dir = os.path.join(_MEIPASS, "frontend", "dist")
    data_dir = os.path.expanduser(
        "~/Library/Application Support/PierreHuygheBale/data"
    )
    for sub in ("timelines", "devices", "orchestrations"):
        os.makedirs(os.path.join(data_dir, sub), exist_ok=True)
else:
    dist_dir = None
    data_dir = None

from app import create_app  # noqa: E402 — must import after path setup

app = create_app(dist_dir=dist_dir, data_dir=data_dir)


def _run_flask():
    app.run(host="127.0.0.1", port=5001, use_reloader=False)


# Start Flask in a daemon thread
server = threading.Thread(target=_run_flask, daemon=True)
server.start()

# Wait for Flask to be ready (up to 5 s)
for _ in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:5001/")
        break
    except Exception:
        time.sleep(0.1)

# Open native macOS window — blocks until closed
webview.create_window(
    "PIERRE HUYGHE BALE",
    "http://127.0.0.1:5001",
    width=1280,
    height=800,
)
webview.start()
