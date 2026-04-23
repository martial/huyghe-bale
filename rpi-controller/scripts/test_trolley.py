#!/usr/bin/env python3
"""Interactive bench test for the trolley controller, run DIRECTLY on the Pi.

Bypasses OSC — calls the same `handle_*` functions the service uses.
Stop the service first so it doesn't fight for the GPIO:

    sudo systemctl stop gpio-osc-trolley
    sudo /opt/gpio-osc/venv/bin/python /opt/gpio-osc/scripts/test_trolley.py

(or from a git checkout: `sudo .venv/bin/python rpi-controller/scripts/test_trolley.py`).

Heads-up: the stepper will move. Confirm the limit-switch wiring works
before running `home` — a broken limit will drive the cart into the end.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import RPi.GPIO as GPIO  # noqa: E402
from _repl import run_repl  # noqa: E402
from controllers import trolley  # noqa: E402


MENU = """
trolley bench test — commands:
  e <0|1>               enable/disable driver (ENA active LOW)
  d <0|1>               direction (0 = reverse toward home, 1 = forward)
  v <0..1>              speed (0 stopped, 1 = MIN_PULSE_DELAY_S)
  step <n>              burst N pulses at current speed/dir
  pos <0..1>            target position (steps = value * TROLLEY_MAX_STEPS)
  stop                  cancel any motion
  home                  reverse until limit switch, position = 0
  s                     print a status snapshot
  m [interval]          live status monitor every N seconds (default 0.5)
  m off                 stop the monitor
  h | ?                 help
  q                     quit
"""


def fmt_status(s: dict) -> str:
    pos = float(s.get("position", 0.0))
    return (
        f"pos={pos * 100:5.1f}%  "
        f"limit={'HIT' if int(s.get('limit', 0)) else ' · '}  "
        f"homed={'yes' if int(s.get('homed', 0)) else 'no '}"
    )


def handle(parts: Sequence[str]) -> None:
    cmd = parts[0].lower()
    if cmd == "e" and len(parts) == 2:
        trolley.handle_enable("/trolley/enable", int(parts[1]))
    elif cmd == "d" and len(parts) == 2:
        trolley.handle_dir("/trolley/dir", int(parts[1]))
    elif cmd == "v" and len(parts) == 2:
        trolley.handle_speed("/trolley/speed", float(parts[1]))
    elif cmd == "step" and len(parts) == 2:
        trolley.handle_step("/trolley/step", int(parts[1]))
    elif cmd == "pos" and len(parts) == 2:
        value = float(parts[1])
        if not 0.0 <= value <= 1.0:
            raise ValueError("pos must be between 0 and 1")
        trolley.handle_position("/trolley/position", value)
    elif cmd == "stop":
        trolley.handle_stop("/trolley/stop")
    elif cmd == "home":
        trolley.handle_home("/trolley/home")
    else:
        print(f"unknown command: {' '.join(parts)!r} — type 'h' for help")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print("Initialising trolley hardware (stepper + limit switch)…")
    trolley.setup(webhooks=None)
    try:
        run_repl(MENU, handle, trolley.get_status, fmt_status)
    finally:
        print("Cleaning up — disabling driver and releasing GPIO…")
        trolley.cleanup()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
