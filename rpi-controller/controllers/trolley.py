"""Trolley controller — STUB.

Hardware spec pending. This module exists so Pis can be installed with
--type=trolley today and report themselves to the admin backend, but no
GPIO work is performed and no OSC addresses are handled yet.

Fill in:
  - pin assignments (move to config.py or keep local)
  - setup(): GPIO.setup + PWM/direction lines
  - register_osc(): OSC addresses per the trolley protocol
  - handle_http_test(): operator-facing HTTP probe
  - cleanup(): safe zero-out
"""

import logging
import time

logger = logging.getLogger(__name__)

NAME = "trolley"

last_osc_time = 0.0
_webhooks = None


def setup(webhooks):
    global _webhooks
    _webhooks = webhooks
    logger.warning("Trolley controller stub — no GPIO initialised. Awaiting hardware spec.")


def cleanup():
    logger.info("Trolley shutdown (stub — nothing to do)")


def register_osc(dispatcher):
    # Intentionally empty. Backend playback is gated to vents-only for now.
    logger.info("Trolley stub: no OSC addresses registered.")


def handle_http_test(body):
    global last_osc_time
    last_osc_time = time.time()
    logger.info("Trolley stub /gpio/test received: %s", body)
    return {"ok": False, "error": "trolley controller is a stub — not implemented"}


def get_last_osc_time():
    return last_osc_time


def describe():
    return {"controller": NAME, "status": "stub"}
