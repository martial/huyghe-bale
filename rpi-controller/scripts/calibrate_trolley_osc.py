#!/usr/bin/env python3
"""Interactive trolley configuration CLI — talks to a live gpio-osc-trolley over OSC.

The trolley no longer requires a physical calibration span. Configure it by
entering the rail length and wheel radius; the firmware derives steps. This
tool also exposes a directional Home command — drive toward either end-stop
until that limit switch trips.

    python rpi-controller/scripts/calibrate_trolley_osc.py --host 192.168.1.74

Sister to scripts/test_trolley.py (direct-GPIO bench tool) — that one bypasses
the firmware; this one drives it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from pythonosc.dispatcher import Dispatcher  # noqa: E402
from pythonosc.osc_server import ThreadingOSCUDPServer  # noqa: E402
from pythonosc.udp_client import SimpleUDPClient  # noqa: E402

import trolley_settings  # noqa: E402

# ── ANSI colour helpers (auto-disable when not a TTY) ──────────────────────

_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def green(s):  return _c("32", s)
def red(s):    return _c("31", s)
def yellow(s): return _c("33", s)
def cyan(s):   return _c("36", s)
def dim(s):    return _c("2", s)
def bold(s):   return _c("1", s)


# ── input helpers (mirrors scripts/test_trolley.py for consistency) ────────

def ask(prompt: str, default: str | None = None) -> str:
    hint = f" [{default}]" if default is not None else ""
    raw = input(f"  {prompt}{hint}: ").strip()
    return raw if raw else (default or "")


def ask_yes(prompt: str, default: bool = False) -> bool:
    raw = ask(prompt, "y" if default else "n").lower()
    return raw.startswith("y")


# ── status state shared with the OSC server thread ─────────────────────────

class State:
    """Mutable snapshot of the latest /trolley/status frame, plus session flags."""

    def __init__(self):
        self.lock = threading.Lock()
        self.last_pong_at: float = 0.0
        self.device_type: str | None = None
        self.hardware_id: str | None = None
        self.position: float = 0.0
        self.limit: int = 0
        self.homed: int = 0
        self.calibrated: int = 0
        self.state: str = "?"
        self.last_status_at: float = 0.0
        self.settings: dict = {}
        self._prev_state: str | None = None

    def update_status(self, position, limit, homed, state, calibrated):
        with self.lock:
            prev = self._prev_state
            self.position = float(position)
            self.limit = int(limit)
            self.homed = int(homed)
            self.calibrated = int(calibrated)
            self.state = str(state)
            self.last_status_at = time.time()
            transition = None
            if prev is not None and prev != state:
                transition = (prev, state)
            self._prev_state = state
            return transition

    def snapshot_line(self) -> str:
        with self.lock:
            age = time.time() - self.last_status_at if self.last_status_at else None
        homed_tag = green("HOMED ✓") if self.homed else red("HOMED ✗")
        cal_tag = green("CFG ✓") if self.calibrated else red("CFG ✗")
        state_tag = (yellow(f"state={self.state:<11}")
                     if self.state == "homing"
                     else cyan(f"state={self.state:<11}"))
        pos_tag = f"POS {self.position * 100:5.1f}%"
        if age is None:
            age_tag = dim("(no /trolley/status yet)")
        elif age > 1.5:
            age_tag = red(f"last {age:.1f}s ago")
        else:
            age_tag = dim(f"last {age:.2f}s ago")
        return f"[{pos_tag} │ {state_tag} │ {homed_tag} │ {cal_tag} │ {age_tag}]"


# ── OSC handlers ───────────────────────────────────────────────────────────

def make_dispatcher(state: State, verbose: bool) -> Dispatcher:
    d = Dispatcher()

    def on_pong(client_address, addr, *args):
        ip = args[0] if args else client_address[0]
        device_type = args[1] if len(args) >= 2 else "unknown"
        hardware_id = args[2] if len(args) >= 3 else ""
        with state.lock:
            state.last_pong_at = time.time()
            state.device_type = str(device_type)
            state.hardware_id = str(hardware_id)
        if verbose:
            print(dim(f"   ← /sys/pong from {ip} type={device_type} id={hardware_id}"))

    def on_status(client_address, addr, *args):
        if len(args) < 3:
            return
        position = args[0]
        limit = args[1]
        homed = args[2]
        s = args[3] if len(args) >= 4 else "idle"
        calibrated = args[4] if len(args) >= 5 else 0
        transition = state.update_status(position, limit, homed, s, calibrated)
        if transition:
            ts = time.strftime("%H:%M:%S")
            prev, curr = transition
            print(f"  {dim(ts)} state: {dim(prev)} → {bold(cyan(str(curr)))}")
        if verbose:
            print(dim(f"   ← /trolley/status pos={position} limit={limit} "
                      f"homed={homed} state={s} calibrated={calibrated}"))

    def on_config(client_address, addr, *args):
        if not args:
            return
        try:
            payload = json.loads(args[0]) if isinstance(args[0], str) else dict(args[0])
        except Exception as e:
            print(red(f"  ✗ /trolley/config parse error: {e}"))
            return
        with state.lock:
            state.settings = payload
        if verbose:
            print(dim(f"   ← /trolley/config {payload}"))

    d.map("/sys/pong", on_pong, needs_reply_address=True)
    d.map("/trolley/status", on_status, needs_reply_address=True)
    d.map("/trolley/config", on_config, needs_reply_address=True)
    if verbose:
        def fallback(client_address, addr, *args):
            print(dim(f"   ← {addr} {list(args)}"))
        d.set_default_handler(fallback, needs_reply_address=True)
    return d


# ── client helpers ─────────────────────────────────────────────────────────

class Client:
    """Wraps SimpleUDPClient with logging."""

    def __init__(self, host: str, port: int, verbose: bool):
        self.host = host
        self.port = port
        self.verbose = verbose
        self._client = SimpleUDPClient(host, port)

    def send(self, address: str, value=None):
        try:
            self._client.send_message(address, value if value is not None else 0)
        except OSError as e:
            print(red(f"  ✗ send failed ({address}): {e} — is the Pi reachable?"))
            return
        if self.verbose:
            print(dim(f"   → {address} {value if value is not None else ''}"))

    def send_pair(self, address: str, key: str, value):
        try:
            self._client.send_message(address, [str(key), value])
        except OSError as e:
            print(red(f"  ✗ send failed ({address}): {e} — is the Pi reachable?"))
            return
        if self.verbose:
            print(dim(f"   → {address} [{key}, {value!r}]"))


# ── menu actions ───────────────────────────────────────────────────────────

def do_home(client: Client, state: State, direction: str):
    client.send("/trolley/home", direction)
    print(yellow(f"  → /trolley/home \"{direction}\" — driving until limit switch"))
    _watch_state(state, want={"idle"}, max_s=30.0, hint="homing")


def do_set_rail_length(client: Client, state: State):
    raw = ask("rail length (mm)")
    try:
        v = float(raw)
    except ValueError:
        print(red("  ✗ not a number"))
        return
    if v <= 0:
        print(red("  ✗ must be > 0"))
        return
    client.send_pair("/trolley/config/set", "rail_length_mm", v)
    client.send("/trolley/config/save")
    print(green(f"  → rail_length_mm = {v} saved"))
    time.sleep(0.3)
    client.send("/trolley/config/get")


def do_set_wheel_radius(client: Client, state: State):
    raw = ask("wheel radius (mm)")
    try:
        v = float(raw)
    except ValueError:
        print(red("  ✗ not a number"))
        return
    if v <= 0:
        print(red("  ✗ must be > 0"))
        return
    client.send_pair("/trolley/config/set", "wheel_radius_mm", v)
    client.send("/trolley/config/save")
    print(green(f"  → wheel_radius_mm = {v} saved"))
    time.sleep(0.3)
    client.send("/trolley/config/get")


def do_config_get(client: Client):
    client.send("/trolley/config/get")
    print(dim("  → /trolley/config/get — see settings echo above"))


def do_config_set(client: Client, state: State):
    keys = list(trolley_settings.ALLOWED_KEYS)
    print("  Valid keys: " + ", ".join(keys))
    key = ask("key")
    if key not in keys:
        print(red(f"  ✗ unknown key: {key!r}"))
        return
    raw = ask(f"value for {key}")
    if raw == "":
        print(red("  ✗ empty value"))
        return
    try:
        if key == "calibration_direction":
            value = trolley_settings._coerce(key, raw)
        else:
            try:
                num = float(raw)
                value = int(num) if num.is_integer() and key in ("steps_per_rev", "microsteps") else num
            except ValueError:
                value = raw
            value = trolley_settings._coerce(key, value)
    except Exception as e:
        print(red(f"  ✗ rejected: {e}"))
        return
    client.send_pair("/trolley/config/set", key, value)
    client.send("/trolley/config/save")
    print(yellow(f"  → {key}={value!r} saved"))
    time.sleep(0.2)
    client.send("/trolley/config/get")


def do_position(client: Client, state: State):
    if state.homed == 0 or state.calibrated == 0:
        print(red(f"  ✗ refusing — needs homed=1 and configured=1 "
                  f"(current homed={state.homed}, configured={state.calibrated})"))
        return
    raw = ask("position 0..1", "0.5")
    try:
        v = float(raw)
    except ValueError:
        print(red("  ✗ not a number"))
        return
    if not (0.0 <= v <= 1.0):
        print(red("  ✗ out of range [0,1]"))
        return
    client.send("/trolley/position", v)
    print(cyan(f"  → /trolley/position {v}"))


def do_stop(client: Client):
    client.send("/trolley/stop")
    print(yellow("  → /trolley/stop"))


# ── short watcher loop ─────────────────────────────────────────────────────

def _watch_state(state: State, want: set[str], max_s: float, hint: str):
    """Print position pulses for up to max_s seconds, until state ∈ want."""
    start = time.time()
    last_print = 0.0
    while time.time() - start < max_s:
        with state.lock:
            now_state = state.state
            pos = state.position
        if now_state in want:
            return
        now = time.time()
        if now - last_print >= 0.5:
            print(dim(f"    {hint}… pos={pos * 100:5.1f}% state={now_state}"))
            last_print = now
        time.sleep(0.1)


# ── bootstrap ──────────────────────────────────────────────────────────────

def bootstrap(host: str, port: int, reply_port: int, verbose: bool) -> tuple[State, ThreadingOSCUDPServer, threading.Thread, Client, int]:
    state = State()
    dispatcher = make_dispatcher(state, verbose)
    server = ThreadingOSCUDPServer(("0.0.0.0", reply_port), dispatcher)
    actual_reply_port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever,
                                     name="osc-listen", daemon=True)
    server_thread.start()

    client = Client(host, port, verbose)
    client.send("/sys/ping", actual_reply_port)
    print(dim(f"   listening for replies on udp/{actual_reply_port}"))

    deadline = time.time() + 3.0
    while time.time() < deadline:
        with state.lock:
            if state.last_pong_at:
                break
        time.sleep(0.05)

    if not state.last_pong_at:
        print(red(f"  ✗ Pi unreachable at {host}:{port} — no /sys/pong in 3s"))
        server.shutdown()
        sys.exit(2)

    print(green(f"  ✓ pong received: type={state.device_type} id={state.hardware_id}"))
    if state.device_type != "trolley":
        print(red(f"  ✗ device at {host} is type={state.device_type!r}, "
                  f"not 'trolley'"))
        server.shutdown()
        sys.exit(3)

    client.send("/trolley/config/get")
    time.sleep(0.4)
    with state.lock:
        if state.settings:
            print(dim("  current settings: "
                      + json.dumps(state.settings, separators=(",", ":"))))
        else:
            print(dim("  (no /trolley/config received yet — old firmware?)"))

    return state, server, server_thread, client, actual_reply_port


# ── main loop ──────────────────────────────────────────────────────────────

MENU = f"""
{bold("━━━ trolley configuration over OSC ━━━")}
  [1] Home reverse {dim("(toward home limit switch)")}
  [2] Home forward {dim("(toward far limit switch)")}
  [3] Set rail length (mm)
  [4] Set wheel radius (mm)
  [5] Re-read settings
  [6] Set a setting (key + value, persists immediately)
  [7] Send /trolley/position {dim("(test configured mapping)")}
  [s] Stop motion
  [q] Quit
""".rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", required=True, help="Pi IP / hostname")
    parser.add_argument("--port", type=int, default=9000,
                        help="Pi OSC port (default 9000)")
    parser.add_argument("--reply-port", type=int, default=0,
                        help="Local UDP port for /trolley/status (default: ephemeral)")
    parser.add_argument("--verbose", action="store_true",
                        help="Mirror every OSC tuple sent and received")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print(bold(f"trolley config CLI → {args.host}:{args.port}"))
    state, server, server_thread, client, reply_port = bootstrap(
        args.host, args.port, args.reply_port, args.verbose,
    )

    actions = {
        "1": ("Home reverse", lambda: do_home(client, state, "reverse")),
        "2": ("Home forward", lambda: do_home(client, state, "forward")),
        "3": ("Set rail length (mm)", lambda: do_set_rail_length(client, state)),
        "4": ("Set wheel radius (mm)", lambda: do_set_wheel_radius(client, state)),
        "5": ("Re-read settings", lambda: do_config_get(client)),
        "6": ("Set a setting", lambda: do_config_set(client, state)),
        "7": ("Send /trolley/position", lambda: do_position(client, state)),
        "s": ("Stop motion", lambda: do_stop(client)),
    }

    try:
        while True:
            print(MENU)
            print("  " + state.snapshot_line())
            try:
                raw = input("\n> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if raw in ("q", "quit", "exit"):
                break
            if raw not in actions:
                print(red(f"  ✗ unknown choice: {raw!r}"))
                continue
            label, fn = actions[raw]
            ts = time.strftime("%H:%M:%S")
            print(f"\n{dim(ts)} {bold(label)}")
            try:
                fn()
            except Exception as e:
                print(red(f"  error: {e}"))
            time.sleep(0.4)
            print("  " + state.snapshot_line())
    finally:
        try:
            client.send("/trolley/stop")
        except Exception:
            pass
        server.shutdown()
        server_thread.join(timeout=1.0)
        print(dim("\nbye"))


if __name__ == "__main__":
    main()
