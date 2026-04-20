"""Vents controller: L298N dual-channel PWM on GPIO12/13, fixed forward direction.

Receives /gpio/a and /gpio/b (float 0.0-1.0) and maps them to PWM duty cycle
on GPIO12 (EnA) and GPIO13 (EnB). Direction pins IN1/IN2/IN3/IN4 are set once
at startup for forward rotation.
"""

import logging
import time

import RPi.GPIO as GPIO

from config import (
    OSC_ADDRESS_A, OSC_ADDRESS_B,
    PWM_FREQUENCY,
    PIN_ENA, PIN_ENB,
    PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4,
)

logger = logging.getLogger(__name__)

NAME = "vents"

pwm_a = None
pwm_b = None
last_value_a = 0.0
last_value_b = 0.0
last_osc_time = 0.0
_webhooks = None


def clamp(value, min_val=0.0, max_val=1.0):
    return max(min_val, min(max_val, value))


def setup(webhooks):
    """Initialize GPIO pins and start PWM at 0% duty cycle."""
    global pwm_a, pwm_b, _webhooks
    _webhooks = webhooks

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for pin, state in [
        (PIN_IN1, GPIO.HIGH),
        (PIN_IN2, GPIO.LOW),
        (PIN_IN3, GPIO.HIGH),
        (PIN_IN4, GPIO.LOW),
    ]:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, state)

    GPIO.setup(PIN_ENA, GPIO.OUT)
    GPIO.setup(PIN_ENB, GPIO.OUT)
    pwm_a = GPIO.PWM(PIN_ENA, PWM_FREQUENCY)
    pwm_b = GPIO.PWM(PIN_ENB, PWM_FREQUENCY)
    pwm_a.start(0)
    pwm_b.start(0)

    logger.info("Vents GPIO: PWM freq=%dHz", PWM_FREQUENCY)
    logger.info("  ENA=%d IN1=%d HIGH IN2=%d LOW", PIN_ENA, PIN_IN1, PIN_IN2)
    logger.info("  ENB=%d IN3=%d HIGH IN4=%d LOW", PIN_ENB, PIN_IN3, PIN_IN4)


def cleanup():
    """Zero outputs and stop PWM. Leaves GPIO.cleanup() to the caller."""
    logger.info("Vents shutdown — zeroing outputs")
    if pwm_a:
        pwm_a.ChangeDutyCycle(0)
        pwm_a.stop()
    if pwm_b:
        pwm_b.ChangeDutyCycle(0)
        pwm_b.stop()
    for pin in (PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4):
        GPIO.output(pin, GPIO.LOW)


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
        if _webhooks:
            _webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


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
        if _webhooks:
            _webhooks.fire("error", {"source": "osc_handler", "error": str(e)})


def register_osc(dispatcher):
    dispatcher.map(OSC_ADDRESS_A, handle_a)
    dispatcher.map(OSC_ADDRESS_B, handle_b)


def handle_http_test(body):
    """Direct GPIO test via HTTP — bypasses OSC entirely."""
    global last_value_a, last_value_b
    va = clamp(float(body.get("value_a", 0.0)))
    vb = clamp(float(body.get("value_b", 0.0)))
    duty_a = round(va * 100.0, 1)
    duty_b = round(vb * 100.0, 1)

    GPIO.output(PIN_IN1, GPIO.HIGH)
    GPIO.output(PIN_IN2, GPIO.LOW)
    pwm_a.ChangeDutyCycle(duty_a)
    last_value_a = duty_a

    GPIO.output(PIN_IN3, GPIO.HIGH)
    GPIO.output(PIN_IN4, GPIO.LOW)
    pwm_b.ChangeDutyCycle(duty_b)
    last_value_b = duty_b

    logger.info("HTTP /gpio/test: a=%.3f (duty %.1f%%) b=%.3f (duty %.1f%%)", va, duty_a, vb, duty_b)
    return {"ok": True, "duty_a": duty_a, "duty_b": duty_b}


def get_last_osc_time():
    return last_osc_time


def describe():
    return {
        "controller": NAME,
        "pwm_freq_hz": PWM_FREQUENCY,
        "channels": {
            "a": {"pwm_pin": PIN_ENA, "dir_pins": [PIN_IN1, PIN_IN2], "osc_address": OSC_ADDRESS_A},
            "b": {"pwm_pin": PIN_ENB, "dir_pins": [PIN_IN3, PIN_IN4], "osc_address": OSC_ADDRESS_B},
        },
    }
