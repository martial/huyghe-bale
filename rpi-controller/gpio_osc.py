#!/usr/bin/env python3
"""OSC-driven controller entry point.

Loads a persistent identity ({type, hardware_id}) from ~/.config/gpio-osc/device.json,
imports the matching controller personality module (vents or trolley), and starts
the OSC server, HTTP status server, and webhooks.

The personality module owns all GPIO/PWM/direction-pin logic; this file owns
transport (OSC, HTTP), process lifecycle, and the /sys/ping↔/sys/pong protocol.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import logging
import time
import http.server
from threading import Event, Thread

import RPi.GPIO as GPIO
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from config import OSC_PORT, HTTP_PORT, TROLLEY_STATUS_HZ
import controllers
import identity
from webhooks import WebhookNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

webhooks = None
controller = None
IDENTITY: dict = {"type": "unknown", "id": ""}  # overwritten in main()
shutdown_event = Event()
last_pinger = None  # (ip, return_port) — used by the trolley status broadcaster


def _service_name() -> str:
    return f"gpio-osc-{IDENTITY['type']}"


# --- Version Info (read once at startup) ---
def _read_git_version():
    cwd = os.path.dirname(os.path.abspath(__file__))
    try:
        h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=cwd).decode("utf-8").strip()
        d = subprocess.check_output(["git", "log", "-1", "--format=%ci", "HEAD"], cwd=cwd).decode("utf-8").strip()
        return {"hash": h, "date": d}
    except Exception:
        return {"hash": "unknown", "date": "unknown"}

VERSION_INFO = _read_git_version()

# --- System Info (read once at startup) ---
def _read_system_info():
    info = {}
    try:
        with open("/proc/device-tree/model", "rb") as f:
            info["model"] = f.read().replace(b"\x00", b"").decode("utf-8").strip()
    except Exception:
        info["model"] = "unknown"
    info["python_version"] = sys.version.split()[0]
    try:
        os_info = {}
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_info[k] = v.strip('"')
        info["os"] = os_info.get("PRETTY_NAME", "unknown")
    except Exception:
        info["os"] = "unknown"
    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
        info["ram_total_mb"] = meminfo.get("MemTotal", 0) // 1024
        info["ram_available_mb"] = meminfo.get("MemAvailable", 0) // 1024
    except Exception:
        info["ram_total_mb"] = 0
        info["ram_available_mb"] = 0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            info["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        info["cpu_temp_c"] = None
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        info["disk_total_mb"] = total // (1024 * 1024)
        info["disk_free_mb"] = free // (1024 * 1024)
    except Exception:
        info["disk_total_mb"] = 0
        info["disk_free_mb"] = 0
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        info["ip"] = "unknown"
    return info

SYSTEM_INFO = _read_system_info()

# --- Heartbeat State ---
start_time = time.time()


class StatusHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path == '/status':
            live = {}
            try:
                with open("/proc/meminfo") as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            meminfo[parts[0].rstrip(":")] = int(parts[1])
                live["ram_available_mb"] = meminfo.get("MemAvailable", 0) // 1024
            except Exception:
                pass
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    live["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
            except Exception:
                pass
            try:
                st = os.statvfs("/")
                live["disk_free_mb"] = (st.f_bavail * st.f_frsize) // (1024 * 1024)
            except Exception:
                pass
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                live["ip"] = s.getsockname()[0]
                s.close()
            except Exception:
                pass
            sys_info = dict(SYSTEM_INFO)
            sys_info.update(live)
            self._send_json({
                "uptime": time.time() - start_time,
                "last_osc": controller.get_last_osc_time() if controller else 0.0,
                "version": VERSION_INFO["hash"],
                "version_date": VERSION_INFO["date"],
                "system_info": sys_info,
                "device_type": IDENTITY["type"],
                "hardware_id": IDENTITY["id"],
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/update':
            self._handle_update()
        elif self.path == '/gpio/test':
            self._handle_gpio_test()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_gpio_test(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length) if length > 0 else b'{}'
            body = json.loads(raw.decode('utf-8'))
            result = controller.handle_http_test(body)
            status = 200 if result.get("ok") else 500
            self._send_json(result, status)
        except Exception as e:
            logger.error("HTTP /gpio/test error: %s", e)
            self._send_json({"ok": False, "error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _handle_update(self):
        global VERSION_INFO
        cwd = os.path.dirname(os.path.abspath(__file__))
        script = os.path.join(cwd, "auto_update.sh")
        try:
            result = subprocess.run(
                ["bash", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, cwd=cwd,
            )
            log_file = "/tmp/gpio-osc-updater.log"
            try:
                with open(log_file) as f:
                    logs = f.read()
            except IOError:
                logs = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
            new_version = _read_git_version()
            VERSION_INFO = new_version
            success = result.returncode == 0
            self._send_json({
                "success": success,
                "logs": logs,
                "new_version": new_version["hash"],
            })
            if success:
                subprocess.Popen(
                    ["sh", "-c", f"sleep 2 && sudo systemctl restart {_service_name()}"],
                    start_new_session=True,
                )
        except subprocess.TimeoutExpired:
            self._send_json({"success": False, "logs": "Update timed out after 120s", "new_version": VERSION_INFO["hash"]}, 500)
        except Exception as e:
            self._send_json({"success": False, "logs": str(e), "new_version": VERSION_INFO["hash"]}, 500)

    def log_message(self, format, *args):
        pass  # Silence HTTP logs

def run_http_server():
    server = http.server.HTTPServer(('0.0.0.0', HTTP_PORT), StatusHandler)
    while not shutdown_event.is_set():
        server.handle_request()


def handle_ping(client_address, address, *args):
    """Reply to /sys/ping with (ip, type, hardware_id) so the backend can identify us."""
    global last_pinger
    if not args:
        return
    try:
        return_port = int(args[0])
        origin_ip = client_address[0]
        last_pinger = (origin_ip, return_port)
        logger.debug("Ping received from %s. Replying to port %d", origin_ip, return_port)
        client = SimpleUDPClient(origin_ip, return_port)
        client.send_message("/sys/pong", [origin_ip, IDENTITY["type"], IDENTITY["id"]])
    except Exception as e:
        logger.error("Handler error on /sys/ping: %s", e)
        if webhooks:
            webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def run_trolley_status_broadcaster():
    """Emit /trolley/status to the last admin that pinged us, at TROLLEY_STATUS_HZ.

    Runs only when the loaded controller exposes get_status(); vents doesn't, so
    the thread exits immediately on other personalities.
    """
    if controller is None or not hasattr(controller, "get_status"):
        return
    period = 1.0 / max(1, TROLLEY_STATUS_HZ)
    while not shutdown_event.is_set():
        try:
            if last_pinger is not None:
                ip, port = last_pinger
                status = controller.get_status()
                client = SimpleUDPClient(ip, port)
                client.send_message(
                    "/trolley/status",
                    [
                        float(status.get("position", 0.0)),
                        int(status.get("limit", 0)),
                        int(status.get("homed", 0)),
                    ],
                )
        except Exception as e:
            logger.debug("Trolley status broadcast error (non-fatal): %s", e)
        shutdown_event.wait(period)


def cleanup(*_):
    """Zero outputs and release GPIO."""
    if shutdown_event.is_set():
        return
    shutdown_event.set()
    logger.info("Shutting down")
    if webhooks:
        webhooks.fire("stop")
    if controller:
        try:
            controller.cleanup()
        except Exception as e:
            logger.error("Controller cleanup error: %s", e)
    try:
        GPIO.cleanup()
    except Exception as e:
        logger.error("GPIO.cleanup error: %s", e)
    logger.info("Cleaned up")
    sys.exit(0)


def main():
    global webhooks, controller, IDENTITY
    IDENTITY = identity.load_or_create()
    webhooks = WebhookNotifier()

    def _crash_hook(exc_type, exc_value, exc_tb):
        logger.critical("Unhandled exception — %s: %s", exc_type.__name__, exc_value)
        webhooks.fire("crash", {"error": "%s: %s" % (exc_type.__name__, exc_value)})
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _crash_hook

    logger.info("Identity: type=%s id=%s", IDENTITY["type"], IDENTITY["id"])

    try:
        controller = controllers.load(IDENTITY["type"])
    except Exception as e:
        logger.critical("Failed to load controller %r: %s", IDENTITY["type"], e)
        webhooks.fire("error", {"source": "controller_load", "error": str(e)})
        raise

    logger.info("Loaded controller: %s", controller.describe())

    try:
        controller.setup(webhooks)
    except Exception as e:
        logger.critical("Controller setup failed: %s", e)
        webhooks.fire("error", {"source": "gpio", "error": str(e)})
        raise

    webhooks.fire("start")
    logger.info("Service started")

    try:
        Thread(target=run_http_server, daemon=True).start()
        logger.info("HTTP Status server listening on 0.0.0.0:%d", HTTP_PORT)
    except Exception as e:
        webhooks.fire("error", {"source": "http_server", "error": str(e)})
        logger.error("Failed to start HTTP status server: %s", e)

    if hasattr(controller, "get_status"):
        Thread(target=run_trolley_status_broadcaster, daemon=True).start()
        logger.info("Trolley status broadcaster started at %d Hz", TROLLEY_STATUS_HZ)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    dispatcher = Dispatcher()
    controller.register_osc(dispatcher)
    dispatcher.map("/sys/ping", handle_ping, needs_reply_address=True)

    try:
        server = BlockingOSCUDPServer(("0.0.0.0", OSC_PORT), dispatcher)
    except OSError as e:
        logger.critical("OSC server failed to bind on port %d: %s", OSC_PORT, e)
        webhooks.fire("error", {"source": "osc_bind", "error": str(e)})
        raise

    logger.info("OSC server listening on 0.0.0.0:%d", OSC_PORT)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical("OSC server crashed: %s", e)
        webhooks.fire("error", {"source": "osc_server", "error": str(e)})
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
