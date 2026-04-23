#!/usr/bin/env python3
"""Interactive vents hardware bench test — direct GPIO, no OSC, no controller.

Pick a numbered action, the script prompts for any needed values.

    sudo systemctl stop gpio-osc-vents     # free up the GPIO
    sudo .venv/bin/python rpi-controller/scripts/test_vents.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

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
W1_GLOB = "/sys/bus/w1/devices/28-*/w1_slave"


# ── input helpers ──────────────────────────────────────────────────────────

def ask(prompt: str, default: str | None = None) -> str:
    hint = f" [{default}]" if default is not None else ""
    raw = input(f"  {prompt}{hint}: ").strip()
    return raw if raw else (default or "")


def ask_int(prompt: str, low: int, high: int, default: int | None = None) -> int:
    while True:
        raw = ask(prompt, str(default) if default is not None else None)
        try:
            v = int(raw)
            if low <= v <= high:
                return v
        except ValueError:
            pass
        print(f"    → must be an integer between {low} and {high}")


def ask_float(prompt: str, low: float, high: float, default: float | None = None) -> float:
    while True:
        raw = ask(prompt, str(default) if default is not None else None)
        try:
            v = float(raw)
            if low <= v <= high:
                return v
        except ValueError:
            pass
        print(f"    → must be a number between {low} and {high}")


# ── hardware ops ───────────────────────────────────────────────────────────

class VentsBench:
    def __init__(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in PEL:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        self.pwms = []
        for pin in FAN_PWM_PINS:
            GPIO.setup(pin, GPIO.OUT)
            p = GPIO.PWM(pin, VENTS_FAN_PWM_FREQ)
            p.start(0)
            self.pwms.append(p)
        for pin in TACHO_PINS:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        os.system("modprobe w1-gpio > /dev/null 2>&1")
        os.system("modprobe w1-therm > /dev/null 2>&1")
        self.duty = [0.0, 0.0]

    def toggle_peltier(self) -> None:
        idx = ask_int("Peltier cell (1-3)", 1, 3, 1)
        state = ask_int("State (0=off, 1=on)", 0, 1, 1)
        GPIO.output(PEL[idx - 1], GPIO.HIGH if state else GPIO.LOW)
        print(f"  → P{idx} = {'ON' if state else 'off'}")

    def set_mask(self) -> None:
        mask = ask_int("Mask (0..7, bit0=P1, bit1=P2, bit2=P3)", 0, 7, 0)
        for i, pin in enumerate(PEL):
            GPIO.output(pin, GPIO.HIGH if mask & (1 << i) else GPIO.LOW)
        print(f"  → P[{mask & 1}{(mask >> 1) & 1}{(mask >> 2) & 1}]")

    def set_fan(self) -> None:
        idx = ask_int("Fan (1=cold, 2=hot)", 1, 2, 1)
        duty = ask_float("Duty %", 0.0, 100.0, self.duty[idx - 1] or 50.0)
        self.pwms[idx - 1].ChangeDutyCycle(duty)
        self.duty[idx - 1] = duty
        print(f"  → Fan{idx} = {duty:.1f}%")

    def read_temps(self) -> None:
        paths = sorted(glob.glob(W1_GLOB))
        if not paths:
            print("  no DS18B20 probes under /sys/bus/w1 — check dtoverlay=w1-gpio")
            return
        for i, p in enumerate(paths, 1):
            short = os.path.basename(os.path.dirname(p))
            try:
                with open(p) as f:
                    lines = f.readlines()
                if not lines or "YES" not in lines[0]:
                    print(f"  probe{i} ({short}): CRC not ready — retry")
                    continue
                eq = lines[1].find("t=")
                t = int(lines[1][eq + 2:].strip()) / 1000.0 if eq >= 0 else None
                print(f"  probe{i} ({short}): {t:.2f}°C" if t is not None else f"  probe{i}: no reading")
            except OSError as e:
                print(f"  probe{i} ({short}): {e}")

    def measure_rpm(self) -> None:
        duration = ask_float("Duration seconds", 0.5, 30.0, 2.0)
        print(f"  counting tacho falling edges for {duration:.1f}s…")
        for pin, label in zip(TACHO_PINS, TACHO_LABELS):
            count = 0
            prev = GPIO.input(pin)
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                cur = GPIO.input(pin)
                if prev == GPIO.HIGH and cur == GPIO.LOW:
                    count += 1
                prev = cur
            # PC fans emit 2 pulses per revolution
            rpm = (count / 2.0) * (60.0 / duration)
            print(f"    tacho{label} (GPIO {pin}): {count} edges → ~{rpm:.0f} RPM")

    def snapshot(self) -> None:
        bits = [GPIO.input(pin) for pin in PEL]
        print(f"  P[{bits[0]}{bits[1]}{bits[2]}]  "
              f"Fan1={self.duty[0]:.1f}%  Fan2={self.duty[1]:.1f}%")

    def all_off(self) -> None:
        for pin in PEL:
            GPIO.output(pin, GPIO.LOW)
        for i, pwm in enumerate(self.pwms):
            pwm.ChangeDutyCycle(0)
            self.duty[i] = 0.0
        print("  → Peltiers OFF, fan PWM 0")

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


# ── menu ───────────────────────────────────────────────────────────────────

MENU_HEADER = "\n━━━ vents bench test ━━━"


def build_menu(b: VentsBench) -> "list[tuple[str, callable]]":
    return [
        ("Toggle a single Peltier cell", b.toggle_peltier),
        ("Set all Peltiers as a bitmask", b.set_mask),
        ("Set fan duty (PWM)",             b.set_fan),
        ("Read DS18B20 temperatures",      b.read_temps),
        ("Measure fan RPM from tachos",    b.measure_rpm),
        ("Print pin snapshot",             b.snapshot),
        ("All off (Peltiers + fans to 0)", b.all_off),
    ]


def main() -> None:
    print(__doc__)
    bench = VentsBench()
    actions = build_menu(bench)
    try:
        while True:
            print(MENU_HEADER)
            for i, (label, _) in enumerate(actions, 1):
                print(f"  [{i}] {label}")
            print("  [q] Quit")
            try:
                raw = input("\n> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if raw in ("q", "quit", "exit"):
                break
            try:
                idx = int(raw)
            except ValueError:
                print("  → enter a number or 'q'")
                continue
            if not 1 <= idx <= len(actions):
                print(f"  → choose 1..{len(actions)} or 'q'")
                continue
            try:
                actions[idx - 1][1]()
            except Exception as e:
                print(f"  error: {e}")
    finally:
        print("\nCleaning up…")
        bench.cleanup()


if __name__ == "__main__":
    main()
