#!/usr/bin/env python3
"""OSC listener that drives L298N motor controller via GPIO PWM.

Receives /gpio/a and /gpio/b messages (float 0.0–1.0) and maps them
to PWM duty cycle on GPIO12 (EnA) and GPIO13 (EnB).
Direction pins are set once at startup for fixed forward rotation.
"""

import json
import os
import signal
import sys
import logging
from threading import Event, Thread

import requests
import RPi.GPIO as GPIO
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from config import (
    OSC_PORT, OSC_ADDRESS_A, OSC_ADDRESS_B,
    PWM_FREQUENCY,
    PIN_ENA, PIN_ENB,
    PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

pwm_a = None
pwm_b = None
shutdown_event = Event()

WEBHOOKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webhooks.json")
webhook_config = []


def load_webhooks():
    global webhook_config
    try:
        with open(WEBHOOKS_PATH) as f:
            webhook_config = json.load(f).get("webhooks", [])
    except Exception:
        webhook_config = []


def fire_webhook(event, data=None):
    """Fire webhook for matching event in a background thread. Never raises."""
    payload = {"event": event}
    if data:
        payload.update(data)
    for hook in webhook_config:
        if event in hook.get("events", []):
            Thread(target=_post_webhook, args=(hook, payload), daemon=True).start()


def _post_webhook(hook, payload):
    try:
        headers = {}
        token = hook.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        requests.post(hook["url"], json=payload, headers=headers, timeout=5)
    except Exception:
        pass


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
    if not args:
        return
    value = clamp(float(args[0]))
    duty = value * 100.0
    pwm_a.ChangeDutyCycle(duty)
    logger.debug("A = %.3f (duty %.1f%%)", value, duty)


def handle_b(address, *args):
    """Handle /gpio/b OSC message."""
    if not args:
        return
    value = clamp(float(args[0]))
    duty = value * 100.0
    pwm_b.ChangeDutyCycle(duty)
    logger.debug("B = %.3f (duty %.1f%%)", value, duty)


def cleanup(*_):
    """Zero all outputs and clean up GPIO."""
    if shutdown_event.is_set():
        return
    shutdown_event.set()
    logger.info("Shutting down — zeroing outputs")
    fire_webhook("stop")
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
    load_webhooks()
    setup_gpio()
    fire_webhook("start")

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    dispatcher = Dispatcher()
    dispatcher.map(OSC_ADDRESS_A, handle_a)
    dispatcher.map(OSC_ADDRESS_B, handle_b)

    server = BlockingOSCUDPServer(("0.0.0.0", OSC_PORT), dispatcher)
    logger.info("OSC server listening on 0.0.0.0:%d", OSC_PORT)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
