#!/usr/bin/env python3
"""Interactive trolley hardware bench test — direct GPIO, no OSC, no controller.

Pick a numbered action, the script prompts for any needed values.

    sudo systemctl stop gpio-osc-trolley   # free up the GPIO
    sudo .venv/bin/python rpi-controller/scripts/test_trolley.py
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import RPi.GPIO as GPIO  # noqa: E402

from config import PIN_STEP_DIR, PIN_STEP_PUL, PIN_STEP_ENA, PIN_LIM_SWITCH  # noqa: E402


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

class TrolleyBench:
    def __init__(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(PIN_STEP_DIR, GPIO.OUT)
        GPIO.setup(PIN_STEP_PUL, GPIO.OUT)
        GPIO.setup(PIN_STEP_ENA, GPIO.OUT)
        GPIO.setup(PIN_LIM_SWITCH, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.output(PIN_STEP_PUL, GPIO.LOW)
        GPIO.output(PIN_STEP_DIR, GPIO.HIGH)
        GPIO.output(PIN_STEP_ENA, GPIO.HIGH)  # disabled

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
        """
        n = ask_int("Number of steps", 1, 1_000_000, 200)
        speed_hz = ask_float("Speed (Hz = steps/sec)", 10.0, 5000.0, 250.0)
        half = (1.0 / speed_hz) / 2.0
        print(f"  stepping {n} steps at {speed_hz:.0f} Hz (half-period {half * 1000:.2f}ms)…")
        start = time.monotonic()
        sent = 0
        for i in range(n):
            if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH:
                print(f"  → limit hit after {sent} steps")
                return
            GPIO.output(PIN_STEP_PUL, GPIO.HIGH)
            time.sleep(half)
            GPIO.output(PIN_STEP_PUL, GPIO.LOW)
            time.sleep(half)
            sent = i + 1
        elapsed = time.monotonic() - start
        print(f"  → {sent} steps in {elapsed:.2f}s (actual {sent / elapsed:.0f} Hz)")

    def read_limit(self) -> None:
        state = GPIO.input(PIN_LIM_SWITCH)
        print(f"  LIM = {'HIT (HIGH)' if state == GPIO.HIGH else 'open (LOW)'}")

    def snapshot(self) -> None:
        d = "forward" if GPIO.input(PIN_STEP_DIR) == GPIO.HIGH else "reverse"
        e = "disabled" if GPIO.input(PIN_STEP_ENA) == GPIO.HIGH else "enabled"
        lim = "HIT" if GPIO.input(PIN_LIM_SWITCH) == GPIO.HIGH else "open"
        print(f"  DIR={d}  ENA={e}  LIM={lim}")

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
        ("Enable / disable driver (ENA)",    b.set_ena),
        ("Set direction (DIR)",              b.set_dir),
        ("Step N times at given speed (Hz)", b.pulse),
        ("Read limit switch",                b.read_limit),
        ("Print pin snapshot",               b.snapshot),
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
