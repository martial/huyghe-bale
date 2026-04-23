"""Shared REPL helper for the vents/trolley bench-test scripts.

Both scripts reuse the same controller code that the systemd service
runs — they just skip the OSC dispatcher and call `handle_*` directly.
"""

from __future__ import annotations

import shlex
import sys
import threading
import time
from typing import Callable, Sequence


def run_repl(
    menu: str,
    handle_command: Callable[[Sequence[str]], None],
    get_status: Callable[[], dict],
    status_fmt: Callable[[dict], str],
) -> None:
    """Blocking REPL. `handle_command` gets tokens from shlex.split.
    `m <n>` launches a background monitor that prints status every N s."""
    stop_monitor = threading.Event()
    monitor_thread: threading.Thread | None = None

    def _start_monitor(interval: float) -> None:
        nonlocal monitor_thread
        _stop_monitor()
        stop_monitor.clear()

        def loop() -> None:
            while not stop_monitor.is_set():
                try:
                    sys.stdout.write(f"\r{status_fmt(get_status())}\n> ")
                    sys.stdout.flush()
                except Exception as e:
                    print(f"monitor error: {e}")
                stop_monitor.wait(interval)

        monitor_thread = threading.Thread(target=loop, daemon=True, name="monitor")
        monitor_thread.start()

    def _stop_monitor() -> None:
        stop_monitor.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=0.5)

    print(menu)
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
                print(menu)
                continue
            if raw == "s":
                print(status_fmt(get_status()))
                continue
            if raw.startswith("m"):
                # `m` → monitor default 1 s; `m 0.5` → every 0.5 s; `m off` → stop.
                tokens = raw.split()
                if len(tokens) == 2 and tokens[1] == "off":
                    _stop_monitor()
                    print("monitor stopped")
                    continue
                interval = float(tokens[1]) if len(tokens) == 2 else 1.0
                _start_monitor(interval)
                print(f"monitor on, every {interval}s (type 'm off' to stop)")
                continue
            try:
                tokens = shlex.split(raw)
                handle_command(tokens)
            except Exception as e:
                print(f"error: {e}")
    finally:
        _stop_monitor()
