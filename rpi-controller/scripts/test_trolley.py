#!/usr/bin/env python3
"""Interactive trolley hardware bench test — direct GPIO, no OSC, no controller.

Pick a numbered action, the script prompts for any needed values.

    sudo systemctl stop gpio-osc-trolley   # free up the GPIO
    sudo ./rpi-controller/venv/bin/python rpi-controller/scripts/test_trolley.py
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import RPi.GPIO as GPIO  # noqa: E402

from config import (  # noqa: E402
    PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA,
    PIN_LIM_SWITCH, PIN_LIM_SWITCH_FAR,
    PIN_ALARM_1, PIN_ALARM_2,
    PIN_PEND_1, PIN_PEND_2,
)


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

_INPUT_PINS = (
    ("LIM_HOME", PIN_LIM_SWITCH),
    ("LIM_FAR",  PIN_LIM_SWITCH_FAR),
    ("ALARM_1",  PIN_ALARM_1),
    ("ALARM_2",  PIN_ALARM_2),
    ("PEND_1",   PIN_PEND_1),
    ("PEND_2",   PIN_PEND_2),
)


class TrolleyBench:
    def __init__(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        # On Pi 5 / rpi-lgpio, GPIO.setup(OUT) without `initial=` reads the
        # pin before claiming it and errors with 'GPIO not allocated'.
        # Passing initial=… skips the read.
        GPIO.setup(PIN_STEP_DIR, GPIO.OUT, initial=GPIO.HIGH)  # default forward
        GPIO.setup(PIN_STEP_PUL, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(PIN_STEP_ENA, GPIO.OUT, initial=GPIO.HIGH)  # disabled (active LOW)
        for _, pin in _INPUT_PINS:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def set_ena(self) -> None:
        state = ask_int("Driver enable (1=enabled/ENA LOW, 0=disabled)", 0, 1, 1)
        GPIO.output(PIN_STEP_ENA, GPIO.LOW if state else GPIO.HIGH)
        print(f"  → ENA = {'enabled (LOW)' if state else 'disabled (HIGH)'}")

    def set_dir(self) -> None:
        d = ask_int("Direction (1=forward, 0=reverse toward home)", 0, 1, 1)
        GPIO.output(PIN_STEP_DIR, GPIO.HIGH if d else GPIO.LOW)
        print(f"  → DIR = {'forward' if d else 'reverse'}")

    def pulse(self) -> None:
        """Drive the stepper for N steps at the chosen speed.

        On the Nema/DM542-style drivers we use, one pulse on PUL = one step.
        Speed is pulse frequency: freq = 1000 / (2 * half_period_ms).
        Aborts on either limit switch (home or far) or any driver alarm.
        """
        n = ask_int("Number of steps", 1, 1_000_000, 200)
        speed_hz = ask_float("Speed (Hz = steps/sec)", 10.0, 5000.0, 250.0)
        half = (1.0 / speed_hz) / 2.0
        print(f"  stepping {n} steps at {speed_hz:.0f} Hz (half-period {half * 1000:.2f}ms)…")
        start = time.monotonic()
        sent = 0
        for i in range(n):
            if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH:
                print(f"  → home limit hit after {sent} steps")
                return
            if GPIO.input(PIN_LIM_SWITCH_FAR) == GPIO.HIGH:
                print(f"  → far limit hit after {sent} steps")
                return
            if GPIO.input(PIN_ALARM_1) == GPIO.HIGH or GPIO.input(PIN_ALARM_2) == GPIO.HIGH:
                a1 = GPIO.input(PIN_ALARM_1)
                a2 = GPIO.input(PIN_ALARM_2)
                print(f"  → driver alarm after {sent} steps (ALARM_1={a1} ALARM_2={a2})")
                return
            GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
            time.sleep(half)
            GPIO.output(PIN_STEP_PUL, GPIO.LOW)
            time.sleep(half)
            sent = i + 1
        elapsed = time.monotonic() - start
        print(f"  → {sent} steps in {elapsed:.2f}s (actual {sent / elapsed:.0f} Hz)")

    def read_limits(self) -> None:
        h = GPIO.input(PIN_LIM_SWITCH)
        f = GPIO.input(PIN_LIM_SWITCH_FAR)
        print(f"  LIM_HOME = {'HIT (HIGH)' if h == GPIO.HIGH else 'open (LOW)'}  (BCM {PIN_LIM_SWITCH})")
        print(f"  LIM_FAR  = {'HIT (HIGH)' if f == GPIO.HIGH else 'open (LOW)'}  (BCM {PIN_LIM_SWITCH_FAR})")

    def read_alarms(self) -> None:
        a1 = GPIO.input(PIN_ALARM_1)
        a2 = GPIO.input(PIN_ALARM_2)
        print(f"  ALARM_1 = {'FAULT (HIGH)' if a1 == GPIO.HIGH else 'ok (LOW)'}  (BCM {PIN_ALARM_1})")
        print(f"  ALARM_2 = {'FAULT (HIGH)' if a2 == GPIO.HIGH else 'ok (LOW)'}  (BCM {PIN_ALARM_2})")

    def read_pend(self) -> None:
        p1 = GPIO.input(PIN_PEND_1)
        p2 = GPIO.input(PIN_PEND_2)
        print(f"  PEND_1 = {p1}  (BCM {PIN_PEND_1})")
        print(f"  PEND_2 = {p2}  (BCM {PIN_PEND_2})")

    def live_monitor(self) -> None:
        """Poll all six diagnostic inputs at 10 Hz for 5 seconds; print changes."""
        duration = 5.0
        period = 0.1
        prev = {name: GPIO.input(pin) for name, pin in _INPUT_PINS}
        print(f"  initial: " + "  ".join(f"{n}={v}" for n, v in prev.items()))
        end = time.monotonic() + duration
        while time.monotonic() < end:
            time.sleep(period)
            for name, pin in _INPUT_PINS:
                cur = GPIO.input(pin)
                if cur != prev[name]:
                    arrow = "↑" if cur > prev[name] else "↓"
                    print(f"  {time.strftime('%H:%M:%S')} {name} {arrow} {prev[name]}→{cur}")
                    prev[name] = cur
        print(f"  final:   " + "  ".join(f"{n}={v}" for n, v in prev.items()))

    def snapshot(self) -> None:
        d = "forward" if GPIO.input(PIN_STEP_DIR) == GPIO.HIGH else "reverse"
        e = "disabled" if GPIO.input(PIN_STEP_ENA) == GPIO.HIGH else "enabled"
        parts = [f"DIR={d}", f"ENA={e}"]
        for name, pin in _INPUT_PINS:
            parts.append(f"{name}={GPIO.input(pin)}")
        print("  " + "  ".join(parts))

    def cleanup(self) -> None:
        try:
            GPIO.output(PIN_STEP_PUL, GPIO.LOW)
            GPIO.output(PIN_STEP_ENA, GPIO.HIGH)
        except Exception:
            pass
        GPIO.cleanup()


# ── menu ───────────────────────────────────────────────────────────────────

MENU_HEADER = "\n━━━ trolley bench test ━━━"


def build_menu(b: TrolleyBench) -> "list[tuple[str, callable]]":
    return [
        ("Enable / disable driver (ENA)",            b.set_ena),
        ("Set direction (DIR)",                      b.set_dir),
        ("Step N times at given speed (Hz)",         b.pulse),
        ("Read both limit switches (HOME / FAR)",    b.read_limits),
        ("Read driver alarms (ALARM_1 / ALARM_2)",   b.read_alarms),
        ("Read PEND inputs (PEND_1 / PEND_2)",       b.read_pend),
        ("Live monitor diagnostic inputs (5 s)",     b.live_monitor),
        ("Print pin snapshot",                       b.snapshot),
    ]


def main() -> None:
    print(__doc__)
    bench = TrolleyBench()
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
        print("\nCleaning up — disabling driver, releasing GPIO…")
        bench.cleanup()


if __name__ == "__main__":
    main()
