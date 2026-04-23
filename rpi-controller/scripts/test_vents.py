#!/usr/bin/env python3
"""Interactive bench test for the vents controller, run DIRECTLY on the Pi.

Bypasses OSC — calls the same `handle_*` functions the service uses, so
wiring / timing bugs show up here too. Stop the service first so it
doesn't fight for the GPIO:

    sudo systemctl stop gpio-osc-vents
    sudo /opt/gpio-osc/venv/bin/python /opt/gpio-osc/scripts/test_vents.py

(or from a git checkout: `sudo .venv/bin/python rpi-controller/scripts/test_vents.py`).

Use `sudo` on older Pi OS where RPi.GPIO needs root. On Pi 5, rpi-lgpio
also works as an unprivileged user.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Sequence

# scripts/ sits under rpi-controller/; make the parent importable
# so `from controllers import vents` works from a source checkout.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import RPi.GPIO as GPIO  # noqa: E402
from _repl import run_repl  # noqa: E402
from controllers import vents  # noqa: E402


MENU = """
vents bench test — commands:
  p <1|2|3> <0|1>       peltier cell on/off (forces mode=raw)
  pm <mask 0..7>        all three peltiers as a bitmask (bit 0 = P1, …)
  f <1|2> <0..1>        fan PWM duty (forces mode=raw)
  mode raw|auto         switch regulation mode
  t <°C>                auto-mode target temperature
  max <°C>              safety max temperature (persisted on the Pi)
  alloff                all peltiers + fans to 0
  s                     print a status snapshot
  m [interval]          live status monitor every N seconds (default 1)
  m off                 stop the monitor
  h | ?                 help
  q                     quit
"""


def fmt_status(s: dict) -> str:
    def ft(v):
        return f"{v:5.1f}" if isinstance(v, (int, float)) and v >= 0 else "  N/A"
    pm = int(s.get("peltier_mask", 0))
    pm_bits = f"{pm & 1}{(pm >> 1) & 1}{(pm >> 2) & 1}"
    return (
        f"[{s.get('state','?'):<12}] mode={s.get('mode','?'):<4} "
        f"t1={ft(s.get('temp1_c'))} t2={ft(s.get('temp2_c'))} "
        f"target={float(s.get('target_c', 0)):4.1f}°C "
        f"max={float(s.get('max_temp_c', 0)):4.1f}°C "
        f"P[{pm_bits}] F1={float(s.get('fan1', 0)):.2f} F2={float(s.get('fan2', 0)):.2f} "
        f"rpm=({s.get('rpm1A', 0)}/{s.get('rpm1B', 0)}, "
        f"{s.get('rpm2A', 0)}/{s.get('rpm2B', 0)})"
    )


def handle(parts: Sequence[str]) -> None:
    cmd = parts[0].lower()
    if cmd == "p" and len(parts) == 3:
        idx = int(parts[1])
        value = int(parts[2])
        {1: vents.handle_peltier_1,
         2: vents.handle_peltier_2,
         3: vents.handle_peltier_3}[idx](f"/vents/peltier/{idx}", value)
    elif cmd == "pm" and len(parts) == 2:
        vents.handle_peltier_mask("/vents/peltier", int(parts[1]))
    elif cmd == "f" and len(parts) == 3:
        idx = int(parts[1])
        value = float(parts[2])
        {1: vents.handle_fan_1, 2: vents.handle_fan_2}[idx](f"/vents/fan/{idx}", value)
    elif cmd == "mode" and len(parts) == 2:
        vents.handle_mode("/vents/mode", parts[1].lower())
    elif cmd == "t" and len(parts) == 2:
        vents.handle_target("/vents/target", float(parts[1]))
    elif cmd == "max" and len(parts) == 2:
        vents.handle_max_temp("/vents/max_temp", float(parts[1]))
    elif cmd == "alloff":
        vents.handle_peltier_mask("/vents/peltier", 0)
        vents.handle_fan_1("/vents/fan/1", 0.0)
        vents.handle_fan_2("/vents/fan/2", 0.0)
    else:
        print(f"unknown command: {' '.join(parts)!r} — type 'h' for help")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print("Initialising vents hardware (Peltiers + fans + tachos + DS18B20)…")
    vents.setup(webhooks=None)
    try:
        run_repl(MENU, handle, vents.get_status, fmt_status)
    finally:
        print("Cleaning up…")
        vents.cleanup()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
