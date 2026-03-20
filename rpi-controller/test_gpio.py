#!/usr/bin/env python3
"""Manual GPIO test — ramps PWM up and down on both channels.

Run on the Pi:
    sudo python3 test_gpio.py
"""

import sys
import time

import RPi.GPIO as GPIO

from config import (
    PWM_FREQUENCY,
    PIN_ENA, PIN_ENB,
    PIN_IN1, PIN_IN2, PIN_IN3, PIN_IN4,
)

RAMP_STEP = 5       # duty % increment
RAMP_DELAY = 0.3    # seconds between steps


def setup():
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
    return pwm_a, pwm_b


def ramp(pwm, label):
    print(f"  {label}: ramping up 0% -> 100%")
    for duty in range(0, 101, RAMP_STEP):
        pwm.ChangeDutyCycle(duty)
        print(f"    {duty}%")
        time.sleep(RAMP_DELAY)

    print(f"  {label}: ramping down 100% -> 0%")
    for duty in range(100, -1, -RAMP_STEP):
        pwm.ChangeDutyCycle(duty)
        print(f"    {duty}%")
        time.sleep(RAMP_DELAY)


def main():
    print("GPIO test — pins ENA=%d ENB=%d  freq=%dHz" % (PIN_ENA, PIN_ENB, PWM_FREQUENCY))
    pwm_a, pwm_b = setup()

    try:
        print("\n[Channel A]")
        ramp(pwm_a, "A")

        print("\n[Channel B]")
        ramp(pwm_b, "B")

        print("\n[Both channels]")
        print("  Ramping up 0% -> 100%")
        for duty in range(0, 101, RAMP_STEP):
            pwm_a.ChangeDutyCycle(duty)
            pwm_b.ChangeDutyCycle(duty)
            print(f"    {duty}%")
            time.sleep(RAMP_DELAY)

        print("  Ramping down 100% -> 0%")
        for duty in range(100, -1, -RAMP_STEP):
            pwm_a.ChangeDutyCycle(duty)
            pwm_b.ChangeDutyCycle(duty)
            print(f"    {duty}%")
            time.sleep(RAMP_DELAY)

        print("\nDone — all tests passed.")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        pwm_a.ChangeDutyCycle(0)
        pwm_b.ChangeDutyCycle(0)
        pwm_a.stop()
        pwm_b.stop()
        GPIO.cleanup()
        print("GPIO cleaned up.")


if __name__ == "__main__":
    main()
