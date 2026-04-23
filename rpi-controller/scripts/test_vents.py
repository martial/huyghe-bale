#!/usr/bin/env python3
"""Interactive vents hardware bench test — direct GPIO, no OSC, no controller.

Drives the exact pins defined in `config.py` so wiring bugs are obvious.
No modes, no auto loop, no persisted prefs — just `GPIO.output` and PWM.

    sudo systemctl stop gpio-osc-vents     # free up the GPIO
    sudo .venv/bin/python rpi-controller/scripts/test_vents.py

Menu:
  p <1|2|3> <0|1>       peltier cell on/off
  pm <mask 0..7>        all three peltiers at once (bit 0 = P1)
  f <1|2> <duty %>      fan PWM duty (0..100)
  temp                  read DS18B20 probes once
  rpm [seconds]         count tacho falling edges for N seconds → RPM
  alloff                peltiers low + fan PWM 0
  s                     print current pin state
  h | ?                 help
  q                     quit
"""

from __future__ import annotations

import glob
import os
import shlex
import sys
import time
from typing import Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import RPi.GPIO as GPIO  # noqa: E402

from config import (  # noqa: E402
    PIN_PELTIER_1, PIN_PELTIER_2, PIN_PELTIER_3,
    PIN_PWM_FAN_1, PIN_PWM_FAN_2,
    PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B,
    PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B,
    VENTS_FAN_PWM_FREQ,
)

PEL = (PIN_PELTIER_1, PIN_PELTIER_2, PIN_PELTIER_3)
FAN_PWM_PINS = (PIN_PWM_FAN_1, PIN_PWM_FAN_2)
TACHO_PINS = (PIN_TACHO_FAN_1A, PIN_TACHO_FAN_1B, PIN_TACHO_FAN_2A, PIN_TACHO_FAN_2B)
TACHO_LABELS = ("1A", "1B", "2A", "2B")

# Each DS18B20 exposes its reading in `w1_slave` under /sys/bus/w1/devices/28-*
W1_GLOB = "/sys/bus/w1/devices/28-*/w1_slave"


def setup() -> list:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in PEL:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    pwms = []
    for pin in FAN_PWM_PINS:
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, VENTS_FAN_PWM_FREQ)
        pwm.start(0)
        pwms.append(pwm)
    for pin in TACHO_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    # 1-wire for the probes — harmless if already loaded.
    os.system("modprobe w1-gpio > /dev/null 2>&1")
    os.system("modprobe w1-therm > /dev/null 2>&1")
    return pwms


def read_ds18b20(path: str) -> float | None:
    try:
        with open(path) as f:
            lines = f.readlines()
        if not lines or "YES" not in lines[0]:
            return None
        eq = lines[1].find("t=")
        if eq < 0:
            return None
        return int(lines[1][eq + 2:].strip()) / 1000.0
    except OSError:
        return None


def count_tacho_edges(pin: int, duration: float) -> int:
    """Poll `pin` for falling edges over `duration` seconds. Simple + blocking
    but fine for a manual RPM check — we don't want ISRs fighting the service."""
    count = 0
    prev = GPIO.input(pin)
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        cur = GPIO.input(pin)
        if prev == GPIO.HIGH and cur == GPIO.LOW:
            count += 1
        prev = cur
    return count


class VentsBench:
    def __init__(self) -> None:
        self.pwms = setup()
        self.duty = [0.0, 0.0]  # last set fan duty, 0..100

    def set_peltier(self, idx: int, on: int) -> None:
        if idx not in (1, 2, 3):
            raise ValueError("peltier index must be 1, 2, or 3")
        GPIO.output(PEL[idx - 1], GPIO.HIGH if on else GPIO.LOW)
        print(f"P{idx} → {'ON' if on else 'off'}")

    def set_mask(self, mask: int) -> None:
        if not 0 <= mask <= 7:
            raise ValueError("mask must be 0..7")
        for i, pin in enumerate(PEL):
            GPIO.output(pin, GPIO.HIGH if mask & (1 << i) else GPIO.LOW)
        print(f"P[{mask & 1}{(mask >> 1) & 1}{(mask >> 2) & 1}]")

    def set_fan(self, idx: int, duty_pct: float) -> None:
        if idx not in (1, 2):
            raise ValueError("fan index must be 1 or 2")
        duty_pct = max(0.0, min(100.0, duty_pct))
        self.pwms[idx - 1].ChangeDutyCycle(duty_pct)
        self.duty[idx - 1] = duty_pct
        print(f"Fan{idx} → {duty_pct:.1f}%")

    def read_temps(self) -> None:
        paths = sorted(glob.glob(W1_GLOB))
        if not paths:
            print("no DS18B20 probes found under /sys/bus/w1 — "
                  "check dtoverlay=w1-gpio and modprobe")
            return
        for i, p in enumerate(paths, 1):
            t = read_ds18b20(p)
            short = os.path.basename(os.path.dirname(p))
            print(f"probe{i} ({short}): {t if t is None else f'{t:.2f}°C'}")

    def read_rpm(self, duration: float) -> None:
        print(f"Counting tacho edges for {duration:.1f}s…")
        for pin, label in zip(TACHO_PINS, TACHO_LABELS):
            edges = count_tacho_edges(pin, duration)
            # PC fans typically produce 2 pulses per revolution
            rpm = (edges / 2.0) * (60.0 / duration)
            print(f"  tacho{label} (GPIO {pin}): {edges} edges → ~{rpm:.0f} RPM")

    def snapshot(self) -> None:
        bits = [GPIO.input(pin) for pin in PEL]
        print(f"P[{bits[0]}{bits[1]}{bits[2]}]  "
              f"Fan1={self.duty[0]:.1f}%  Fan2={self.duty[1]:.1f}%")

    def all_off(self) -> None:
        self.set_mask(0)
        self.set_fan(1, 0)
        self.set_fan(2, 0)

    def cleanup(self) -> None:
        try:
            self.all_off()
        except Exception:
            pass
        for pwm in self.pwms:
            try:
                pwm.stop()
            except Exception:
                pass
        GPIO.cleanup()


def handle(b: VentsBench, parts: Sequence[str]) -> None:
    cmd = parts[0].lower()
    if cmd == "p" and len(parts) == 3:
        b.set_peltier(int(parts[1]), int(parts[2]))
    elif cmd == "pm" and len(parts) == 2:
        b.set_mask(int(parts[1]))
    elif cmd == "f" and len(parts) == 3:
        b.set_fan(int(parts[1]), float(parts[2]))
    elif cmd == "temp":
        b.read_temps()
    elif cmd == "rpm":
        duration = float(parts[1]) if len(parts) == 2 else 2.0
        b.read_rpm(duration)
    elif cmd == "alloff":
        b.all_off()
    elif cmd == "s":
        b.snapshot()
    else:
        print(f"unknown command: {' '.join(parts)!r}")


def main() -> None:
    print(__doc__)
    bench = VentsBench()
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
                handle(bench, shlex.split(raw))
            except Exception as e:
                print(f"error: {e}")
    finally:
        print("Cleaning up…")
        bench.cleanup()


if __name__ == "__main__":
    main()
