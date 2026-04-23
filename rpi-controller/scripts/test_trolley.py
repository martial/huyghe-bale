#!/usr/bin/env python3
"""Interactive trolley hardware bench test — direct GPIO, no OSC, no controller.

Drives DIR / PUL / ENA and reads the limit switch directly.

    sudo systemctl stop gpio-osc-trolley   # free up the GPIO
    sudo .venv/bin/python rpi-controller/scripts/test_trolley.py

Menu:
  e <0|1>               ENA pin (active LOW → 0 = driver enabled, 1 = disabled)
  d <0|1>               DIR pin (0 = reverse toward home, 1 = forward)
  pulse <n> [delay_ms]  send N step pulses, 2 ms between edges by default
  lim                   read limit switch state (HIGH = at limit)
  s                     print DIR / ENA / LIM state
  h | ?                 help
  q                     quit

The `pulse` command stops early if the limit switch goes HIGH. For the
trolley's typical Nema driver a 2 ms half-period ≈ 250 Hz pulse rate.
"""

from __future__ import annotations

import os
import shlex
import sys
import time
from typing import Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import RPi.GPIO as GPIO  # noqa: E402

from config import PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, PIN_LIM_SWITCH  # noqa: E402


def setup() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(PIN_STEP_DIR, GPIO.OUT)
    GPIO.setup(PIN_STEP_PUL, GPIO.OUT)
    GPIO.setup(PIN_STEP_ENA, GPIO.OUT)
    GPIO.setup(PIN_LIM_SWITCH, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.output(PIN_STEP_PUL, GPIO.LOW)
    GPIO.output(PIN_STEP_DIR, GPIO.HIGH)
    GPIO.output(PIN_STEP_ENA, GPIO.HIGH)  # disabled


def set_ena(enabled: int) -> None:
    # Driver is active LOW: arg 1 = enabled (pin LOW), 0 = disabled (pin HIGH)
    GPIO.output(PIN_STEP_ENA, GPIO.LOW if enabled else GPIO.HIGH)
    print(f"ENA → {'enabled (LOW)' if enabled else 'disabled (HIGH)'}")


def set_dir(direction: int) -> None:
    GPIO.output(PIN_STEP_DIR, GPIO.HIGH if direction else GPIO.LOW)
    print(f"DIR → {'forward (HIGH)' if direction else 'reverse (LOW)'}")


def pulse(n: int, delay_ms: float) -> None:
    """Send `n` pulses on PUL with `delay_ms` between each edge. Aborts
    if the limit switch goes HIGH — the cart is at the end."""
    if n <= 0:
        print("n must be > 0")
        return
    half = delay_ms / 1000.0
    start = time.monotonic()
    sent = 0
    for i in range(n):
        if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH:
            print(f"limit hit after {sent} pulses")
            return
        GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
        time.sleep(half)
        GPIO.output(PIN_STEP_PUL, GPIO.LOW)
        time.sleep(half)
        sent = i + 1
    elapsed = time.monotonic() - start
    print(f"sent {sent} pulses in {elapsed:.2f}s ({sent/elapsed:.0f} Hz)")


def snapshot() -> None:
    d = "forward" if GPIO.input(PIN_STEP_DIR) == GPIO.HIGH else "reverse"
    e = "disabled" if GPIO.input(PIN_STEP_ENA) == GPIO.HIGH else "enabled"
    lim = "HIT" if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH else "open"
    print(f"DIR={d}  ENA={e}  LIM={lim}")


def handle(parts: Sequence[str]) -> None:
    cmd = parts[0].lower()
    if cmd == "e" and len(parts) == 2:
        set_ena(int(parts[1]))
    elif cmd == "d" and len(parts) == 2:
        set_dir(int(parts[1]))
    elif cmd == "pulse" and 2 <= len(parts) <= 3:
        n = int(parts[1])
        delay_ms = float(parts[2]) if len(parts) == 3 else 2.0
        pulse(n, delay_ms)
    elif cmd == "lim":
        print("LIM", "HIT" if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH else "open")
    elif cmd == "s":
        snapshot()
    else:
        print(f"unknown command: {' '.join(parts)!r}")


def main() -> None:
    print(__doc__)
    setup()
    try:
        while True:
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not raw:
                continue
            if raw in ("q", "quit", "exit"):
                break
            if raw in ("?", "h", "help"):
                print(__doc__)
                continue
            try:
                handle(shlex.split(raw))
            except Exception as e:
                print(f"error: {e}")
    finally:
        print("Cleaning up — disabling driver, releasing GPIO…")
        try:
            GPIO.output(PIN_STEP_PUL, GPIO.LOW)
            GPIO.output(PIN_STEP_ENA, GPIO.HIGH)
        except Exception:
            pass
        GPIO.cleanup()


if __name__ == "__main__":
    main()
