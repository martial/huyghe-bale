#!/usr/bin/env python3
"""OSC listener that drives L298N motor controller via GPIO PWM.

Receives /gpio/a and /gpio/b messages (float 0.0–1.0) and maps them
to PWM duty cycle on GPIO12 (EnA) and GPIO13 (EnB).
Direction pins are set once at startup for fixed forward rotation.
"""

import json
import signal
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

# --- Heartbeat State ---
start_time = time.time()
last_osc_time = 0.0

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            data = {"uptime": time.time() - start_time, "last_osc": last_osc_time}
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass # Silence HTTP logs

def run_http_server():
    server = http.server.HTTPServer(('0.0.0.0', 9001), StatusHandler)
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
    global last_osc_time
    try:
        last_osc_time = time.time()
        if not args:
            return
        value = clamp(float(args[0]))
        duty = value * 100.0
        pwm_a.ChangeDutyCycle(duty)
        logger.debug("A = %.3f (duty %.1f%%)", value, duty)
    except Exception as e:
        logger.error("Handler error on /gpio/a: %s", e)
        webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def handle_b(address, *args):
    """Handle /gpio/b OSC message."""
    global last_osc_time
    try:
        last_osc_time = time.time()
        if not args:
            return
        value = clamp(float(args[0]))
        duty = value * 100.0
        pwm_b.ChangeDutyCycle(duty)
        logger.debug("B = %.3f (duty %.1f%%)", value, duty)
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
        logger.debug(f"Ping received from {origin_ip}. Replying to port {return_port}")
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
        webhooks.fire("crash", {"error": f"{exc_type.__name__}: {exc_value}"})
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
        logger.info("HTTP Status server listening on 0.0.0.0:9001")
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
