#!/usr/bin/env python3
"""OSC listener that drives L298N motor controller via GPIO PWM.

Receives /gpio/a and /gpio/b messages (float 0.0–1.0) and maps them
to PWM duty cycle on GPIO12 (EnA) and GPIO13 (EnB).
Direction pins are set once at startup for fixed forward rotation.
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

from config import (
    OSC_PORT, OSC_ADDRESS_A, OSC_ADDRESS_B,
    PWM_FREQUENCY,
    PIN_ENA, PIN_ENB,
    PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4,
    HTTP_PORT,
)
from webhooks import WebhookNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

pwm_a = None
pwm_b = None
webhooks = None
shutdown_event = Event()
last_value_a = 0.0
last_value_b = 0.0

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
    # Pi model
    try:
        with open("/proc/device-tree/model", "rb") as f:
            info["model"] = f.read().replace(b"\x00", b"").decode("utf-8").strip()
    except Exception:
        info["model"] = "unknown"
    # Python version
    info["python_version"] = sys.version.split()[0]
    # OS
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
    # Total + available RAM (from /proc/meminfo)
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
    # CPU temperature
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            info["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        info["cpu_temp_c"] = None
    # Disk usage
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        info["disk_total_mb"] = total // (1024 * 1024)
        info["disk_free_mb"] = free // (1024 * 1024)
    except Exception:
        info["disk_total_mb"] = 0
        info["disk_free_mb"] = 0
    # Local IP address
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
last_osc_time = 0.0

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path == '/status':
            # Refresh dynamic values (RAM, temp, disk)
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
                "last_osc": last_osc_time,
                "version": VERSION_INFO["hash"],
                "version_date": VERSION_INFO["date"],
                "system_info": sys_info,
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/update':
            self._handle_update()
        else:
            self.send_response(404)
            self.end_headers()

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
            # Read detailed log
            log_file = "/tmp/gpio-osc-updater.log"
            try:
                with open(log_file) as f:
                    logs = f.read()
            except IOError:
                logs = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
            # Read new version after update
            new_version = _read_git_version()
            VERSION_INFO = new_version
            success = result.returncode == 0
            self._send_json({
                "success": success,
                "logs": logs,
                "new_version": new_version["hash"],
            })
            if success:
                # Schedule delayed restart so the response gets sent first
                subprocess.Popen(
                    ["sh", "-c", "sleep 2 && sudo systemctl restart gpio-osc"],
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


def setup_gpio():
    """Initialize GPIO pins and start PWM at 0% duty cycle."""
    global pwm_a, pwm_b

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Direction pins — fixed forward
    for pin, state in [
        (PIN_IN1, GPIO.HIGH),
        (PIN_IN2, GPIO.LOW),
        (PIN_IN3, GPIO.HIGH),
        (PIN_IN4, GPIO.LOW),
    ]:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, state)

    # PWM pins
    GPIO.setup(PIN_ENA, GPIO.OUT)
    GPIO.setup(PIN_ENB, GPIO.OUT)
    pwm_a = GPIO.PWM(PIN_ENA, PWM_FREQUENCY)
    pwm_b = GPIO.PWM(PIN_ENB, PWM_FREQUENCY)
    pwm_a.start(0)
    pwm_b.start(0)

    logger.info("GPIO initialized — PWM on pins %d/%d, direction set forward", PIN_ENA, PIN_ENB)


def clamp(value, min_val=0.0, max_val=1.0):
    return max(min_val, min(max_val, value))


def handle_a(address, *args):
    """Handle /gpio/a OSC message."""
    global last_osc_time, last_value_a
    try:
        last_osc_time = time.time()
        if not args:
            return
        value = clamp(float(args[0]))
        duty = round(value * 100.0, 1)
        logger.info("OSC /gpio/a: %.3f", value)
        GPIO.output(PIN_IN1, GPIO.HIGH)
        GPIO.output(PIN_IN2, GPIO.LOW)
        pwm_a.ChangeDutyCycle(duty)
        if duty != last_value_a:
            logger.info("GPIO A: duty %.1f%% -> %.1f%%", last_value_a, duty)
            last_value_a = duty
    except Exception as e:
        logger.error("Handler error on /gpio/a: %s", e)
        webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def handle_b(address, *args):
    """Handle /gpio/b OSC message."""
    global last_osc_time, last_value_b
    try:
        last_osc_time = time.time()
        if not args:
            return
        value = clamp(float(args[0]))
        duty = round(value * 100.0, 1)
        logger.info("OSC /gpio/b: %.3f", value)
        GPIO.output(PIN_IN3, GPIO.HIGH)
        GPIO.output(PIN_IN4, GPIO.LOW)
        pwm_b.ChangeDutyCycle(duty)
        if duty != last_value_b:
            logger.info("GPIO B: duty %.1f%% -> %.1f%%", last_value_b, duty)
            last_value_b = duty
    except Exception as e:
        logger.error("Handler error on /gpio/b: %s", e)
        webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def handle_ping(client_address, address, *args):
    """Handle /sys/ping OSC message. args[0] should be the return port."""
    if not args:
        return
    try:
        return_port = int(args[0])
        origin_ip = client_address[0]
        logger.debug("Ping received from %s. Replying to port %d", origin_ip, return_port)
        client = SimpleUDPClient(origin_ip, return_port)
        client.send_message("/sys/pong", origin_ip)
    except Exception as e:
        logger.error("Handler error on /sys/ping: %s", e)
        webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def cleanup(*_):
    """Zero all outputs and clean up GPIO."""
    if shutdown_event.is_set():
        return
    shutdown_event.set()
    logger.info("Shutting down — zeroing outputs")
    webhooks.fire("stop")
    if pwm_a:
        pwm_a.ChangeDutyCycle(0)
        pwm_a.stop()
    if pwm_b:
        pwm_b.ChangeDutyCycle(0)
        pwm_b.stop()
    for pin in (PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4):
        GPIO.output(pin, GPIO.LOW)
    GPIO.cleanup()
    logger.info("GPIO cleaned up")
    sys.exit(0)


def main():
    global webhooks
    webhooks = WebhookNotifier()

    # Global crash handler — catches any unhandled exception before process dies
    def _crash_hook(exc_type, exc_value, exc_tb):
        logger.critical("Unhandled exception — %s: %s", exc_type.__name__, exc_value)
        webhooks.fire("crash", {"error": "%s: %s" % (exc_type.__name__, exc_value)})
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _crash_hook

    try:
        setup_gpio()
    except Exception as e:
        logger.critical("GPIO initialization failed: %s", e)
        webhooks.fire("error", {"source": "gpio", "error": str(e)})
        raise

    webhooks.fire("start")
    logger.info("Service started")

    # Start HTTP status server
    try:
        Thread(target=run_http_server, daemon=True).start()
        logger.info("HTTP Status server listening on 0.0.0.0:%d", HTTP_PORT)
    except Exception as e:
        webhooks.fire("error", {"source": "http_server", "error": str(e)})
        logger.error("Failed to start HTTP status server: %s", e)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    dispatcher = Dispatcher()
    dispatcher.map(OSC_ADDRESS_A, handle_a)
    dispatcher.map(OSC_ADDRESS_B, handle_b)
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
