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
    if sys.platform == "win32":
        data_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "PierreHuygheBale",
            "data",
        )
    else:
        data_dir = os.path.expanduser(
            "~/Library/Application Support/PierreHuygheBale/data"
        )
    for sub in ("timelines", "devices", "orchestrations", "trolley_timelines"):
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


# Open native macOS window — blocks until closed
webview.create_window(
    "PIERRE HUYGHE BALE",
    "http://127.0.0.1:5001",
    width=1280,
    height=800,
    js_api=Api(),
)
webview.start()
