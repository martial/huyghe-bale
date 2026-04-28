#!/usr/bin/env python3
"""Interactive trolley calibration CLI — talks to a live gpio-osc-trolley over OSC.

Walks an operator through Home → Calibrate → Save with live status feedback
from the Pi's /trolley/status broadcasts. Useful for rig commissioning when the
admin web UI isn't available, and as an ad-hoc smoke test for the calibration
state machine.

    python rpi-controller/scripts/calibrate_trolley_osc.py --host 192.168.1.74

Sister to scripts/test_trolley.py (direct-GPIO bench tool) — that one bypasses
the firmware; this one drives it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
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
        # Status fields (defaulted to a not-seen-yet shape).
        self.position: float = 0.0
        self.limit: int = 0
        self.homed: int = 0
        self.calibrated: int = 0
        self.state: str = "?"
        self.last_status_at: float = 0.0
        # Settings reported by /trolley/config.
        self.settings: dict = {}
        # Session flag: did we successfully send a calibrate/stop?
        self.candidate_recorded: bool = False
        # Logged state transitions.
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
            return transition  # caller logs outside the lock

    def snapshot_line(self) -> str:
        with self.lock:
            age = time.time() - self.last_status_at if self.last_status_at else None
        homed_tag = green("HOMED ✓") if self.homed else red("HOMED ✗")
        cal_tag = green("CAL ✓") if self.calibrated else red("CAL ✗")
        state_tag = (yellow(f"state={self.state:<11}")
                     if self.state == "calibrating"
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
        # Old firmware sends 3-arg status; new firmware sends 5-arg.
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
    # Catch-all so unexpected addresses are visible in verbose mode.
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

def do_home(client: Client, state: State):
    client.send("/trolley/home")
    print(yellow("  → /trolley/home — driving toward limit switch (watch the carriage)"))
    _watch_state(state, want={"idle"}, max_s=15.0, hint="homing")


def do_calibrate_start(client: Client, state: State, direction: str):
    if state.homed == 0:
        print(red(f"  ✗ refusing — /trolley/status shows homed=0. Run [1] Home first."))
        return
    state.candidate_recorded = False
    client.send("/trolley/calibrate/start", direction)
    print(yellow(f"  → /trolley/calibrate/start \"{direction}\" sent — "
                 f"watch the carriage. Click [4] Stop here near the far end."))


def do_calibrate_stop(client: Client, state: State):
    client.send("/trolley/calibrate/stop")
    state.candidate_recorded = True
    print(yellow("  → /trolley/calibrate/stop sent — candidate recorded on the Pi."))
    _watch_state(state, want={"calibrating"}, max_s=2.0, hint="awaiting stop")


def do_calibrate_save(client: Client, state: State):
    if not state.candidate_recorded and state.state != "calibrating":
        if not ask_yes("No candidate recorded in this session. Save anyway?", default=False):
            return
    client.send("/trolley/calibrate/save")
    print(green("  → /trolley/calibrate/save sent."))
    # Re-read settings so the rail_length_steps update is visible.
    time.sleep(0.3)
    client.send("/trolley/config/get")


def do_calibrate_cancel(client: Client, state: State):
    client.send("/trolley/calibrate/cancel")
    state.candidate_recorded = False
    print(yellow("  → /trolley/calibrate/cancel sent."))


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
    # Client-side coerce + validate using the firmware's own validator.
    try:
        if key == "calibration_direction":
            value = trolley_settings._coerce(key, raw)
        else:
            # Numbers come through as strings on the OSC wire; coerce to native first.
            try:
                num = float(raw)
                value = int(num) if num.is_integer() and key != "soft_limit_pct" else num
            except ValueError:
                value = raw
            value = trolley_settings._coerce(key, value)
    except Exception as e:
        print(red(f"  ✗ rejected: {e}"))
        return
    client.send_pair("/trolley/config/set", key, value)
    print(yellow(f"  → staged {key}={value!r} (call [9?] config/save to persist… "
                 f"actually doing it now)"))
    client.send("/trolley/config/save")
    time.sleep(0.2)
    client.send("/trolley/config/get")


def do_position(client: Client, state: State):
    if state.homed == 0 or state.calibrated == 0:
        print(red(f"  ✗ refusing — needs homed=1 and calibrated=1 "
                  f"(current homed={state.homed}, calibrated={state.calibrated})"))
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
    """Print position pulses for up to max_s seconds, until state ∈ want.
    'want' is the *terminal* state we stop watching at."""
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
    # `port=0` → kernel picks an ephemeral free port.
    server = ThreadingOSCUDPServer(("0.0.0.0", reply_port), dispatcher)
    actual_reply_port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever,
                                     name="osc-listen", daemon=True)
    server_thread.start()

    client = Client(host, port, verbose)
    client.send("/sys/ping", actual_reply_port)
    print(dim(f"   listening for replies on udp/{actual_reply_port}"))

    # Wait up to 3 s for a pong.
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
                  f"not 'trolley' — calibration handlers aren't registered there"))
        server.shutdown()
        sys.exit(3)

    # Pull current settings.
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
{bold("━━━ trolley calibration over OSC ━━━")}
  [1] Home (drive toward limit switch)
  [2] Start calibration {dim("(forward — DIR pin HIGH drives away from home)")}
  [3] Start calibration {dim("(reverse — DIR pin LOW drives away from home)")}
  [4] Stop here {dim("(record candidate rail_length_steps)")}
  [5] Save calibration {dim("(persist to device.json)")}
  [6] Cancel calibration
  [7] Re-read settings
  [8] Set a setting (key + value, persists immediately)
  [9] Send /trolley/position {dim("(test calibrated mapping)")}
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

    print(bold(f"trolley calibration CLI → {args.host}:{args.port}"))
    state, server, server_thread, client, reply_port = bootstrap(
        args.host, args.port, args.reply_port, args.verbose,
    )

    actions = {
        "1": ("Home", lambda: do_home(client, state)),
        "2": ("Start calibration (forward)",
              lambda: do_calibrate_start(client, state, "forward")),
        "3": ("Start calibration (reverse)",
              lambda: do_calibrate_start(client, state, "reverse")),
        "4": ("Stop here", lambda: do_calibrate_stop(client, state)),
        "5": ("Save calibration", lambda: do_calibrate_save(client, state)),
        "6": ("Cancel calibration", lambda: do_calibrate_cancel(client, state)),
        "7": ("Re-read settings", lambda: do_config_get(client)),
        "8": ("Set a setting", lambda: do_config_set(client, state)),
        "9": ("Send /trolley/position", lambda: do_position(client, state)),
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
            # Brief pause so the next snapshot reflects the action's outcome.
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
