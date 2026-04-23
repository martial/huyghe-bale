"""Playback engine — evaluates timeline curves and sends OSC at ~30Hz."""

import time
import threading
import logging
from typing import Optional

from engine.interpolation import evaluate_lane
from engine.osc_sender import OscSender

logger = logging.getLogger(__name__)


class PlaybackEngine:
    """Runs timeline or orchestration playback in a background thread."""

    def __init__(self, tick_rate: int = 30):
        self.tick_rate = tick_rate
        self.osc = OscSender()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # State
        self.playing = False
        self.paused = False
        self.elapsed = 0.0
        self.total_duration = 0.0
        self.current_values = {"a": 0.0, "b": 0.0}
        self._playback_type: Optional[str] = None
        self._playback_id: Optional[str] = None
        self._devices: list[dict] = []
        self._timeline: Optional[dict] = None
        self._orchestration: Optional[dict] = None
        self._resolved_timelines: dict[str, dict] = {}
        self._current_step_index = 0
        self._pause_event = threading.Event()  # Set = running, Clear = paused
        self._pause_event.set()
        self.output_cap = 100  # Max output percentage (1–100)
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        with self._lock:
            return {
                "playing": self.playing,
                "paused": self.paused,
                "elapsed": round(self.elapsed, 3),
                "total_duration": round(self.total_duration, 3),
                "current_values": {k: round(v, 4) for k, v in self.current_values.items()},
                "type": self._playback_type,
                "id": self._playback_id,
                "last_error": self._last_error,
            }

    def start_timeline(self, timeline: dict, devices: list[dict]):
        """Start playing a single timeline to the given devices."""
        self.stop()
        with self._lock:
            self._playback_type = "timeline"
            self._playback_id = timeline.get("id")
            self._timeline = timeline
            self._devices = devices
            self.total_duration = timeline.get("duration", 0.0)
            self.elapsed = 0.0
            self.playing = True
            self._last_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_timeline, daemon=True)
        self._thread.start()
        # Log targets + curve shape so journalctl makes it obvious whether
        # the timeline is actually carrying data and hitting the right IPs.
        lanes = timeline.get("lanes", {})
        a_pts = len((lanes.get("a") or {}).get("points", []))
        b_pts = len((lanes.get("b") or {}).get("points", []))
        ips = ", ".join(f"{d.get('ip_address')}:{d.get('osc_port', 9000)}" for d in devices)
        logger.info(
            "Playback started: timeline %s (%.1fs, a=%dpts b=%dpts, cap=%d%%, tick=%dHz) → %s",
            timeline.get("id"), self.total_duration, a_pts, b_pts,
            self.output_cap, self.tick_rate, ips or "(no devices)",
        )

    def start_trolley_timeline(self, timeline: dict, devices: list[dict]):
        """Start playing a trolley position timeline.

        Timeline schema has a single `lane` with points whose value is position
        along the rail (0..1). Sent as /trolley/position on each tick.
        """
        self.stop()
        with self._lock:
            self._playback_type = "trolley-timeline"
            self._playback_id = timeline.get("id")
            self._timeline = timeline
            self._devices = devices
            self.total_duration = timeline.get("duration", 0.0)
            self.elapsed = 0.0
            self.playing = True
            self._last_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_trolley_timeline, daemon=True)
        self._thread.start()
        raw_events = timeline.get("events") or []
        valid = [ev for ev in raw_events if isinstance(ev, dict)
                 and ev.get("command") in self._TROLLEY_EVENT_ORDER]
        dropped = len(raw_events) - len(valid)
        has_enable_1 = any(ev.get("command") == "enable" and int(ev.get("value") or 0) == 1 for ev in valid)
        ips = ", ".join(f"{d.get('ip_address')}:{d.get('osc_port', 9000)}" for d in devices)
        logger.info(
            "Playback started: trolley-timeline %s (%.1fs, %d events%s%s) → %s",
            timeline.get("id"), self.total_duration, len(valid),
            f", {dropped} dropped (unknown command)" if dropped else "",
            "" if has_enable_1 else " ⚠ no 'enable 1' event — driver stays disabled",
            ips or "(no devices)",
        )

    def start_orchestration(self, orchestration: dict, resolved_timelines: dict, devices_map: dict):
        """Start playing an orchestration (sequential steps).

        Args:
            orchestration: Orchestration dict with steps.
            resolved_timelines: Dict of timeline_id -> timeline dict.
            devices_map: Dict of device_id -> device dict.
        """
        self.stop()
        with self._lock:
            self._playback_type = "orchestration"
            self._playback_id = orchestration.get("id")
            self._orchestration = orchestration
            self._resolved_timelines = resolved_timelines
            self._devices_map = devices_map
            self._current_step_index = 0

            # Calculate total duration
            total = 0.0
            for step in orchestration.get("steps", []):
                total += step.get("delay_before", 0.0)
                tl = resolved_timelines.get(step.get("timeline_id"))
                if tl:
                    total += tl.get("duration", 0.0)
            self.total_duration = total
            self.elapsed = 0.0
            self.playing = True
            self._last_error = None

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_orchestration, daemon=True)
        self._thread.start()
        logger.info("Playback started: orchestration %s", orchestration.get("id"))

    def pause(self):
        """Pause playback, keeping position and outputs."""
        with self._lock:
            if not self.playing or self.paused:
                return
            self.paused = True
            self._pause_elapsed = self.elapsed
        self._pause_event.clear()
        logger.info("Playback paused at %.1fs", self._pause_elapsed)

    def resume(self):
        """Resume playback from paused position."""
        with self._lock:
            if not self.playing or not self.paused:
                return
            self.paused = False
            # Adjust seek offset so elapsed continues from where we paused
            self._seek_offset = self._pause_elapsed - (time.monotonic() - self._start_time)
        self._pause_event.set()
        logger.info("Playback resumed from %.1fs", self._pause_elapsed)

    def stop(self):
        """Stop playback and zero / halt all outputs appropriately for the type."""
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused so thread can exit
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self.paused = False
            was_trolley = self._playback_type == "trolley-timeline"
            for device in self._devices:
                try:
                    ip = device["ip_address"]
                    port = device.get("osc_port", 9000)
                    if was_trolley or device.get("type") == "trolley":
                        self.osc.send(ip, port, "/trolley/stop", 0)
                    else:
                        self.osc.send_zero(ip, port)
                except Exception as e:
                    logger.warning("Failed to halt device %s: %s", device.get("id"), e)

            self.playing = False
            self.elapsed = 0.0
            self.current_values = {"a": 0.0, "b": 0.0}
            self._timeline = None
            self._orchestration = None
            self._devices = []
            self._playback_type = None
            self._playback_id = None

        logger.info("Playback stopped")

    def reload_timeline(self, timeline: dict):
        """Hot-reload timeline data while playing (e.g. after a save).

        Works for both vents timelines and trolley timelines — we only compare
        on the playback id, which is unique per run.
        """
        with self._lock:
            if not self.playing or self._playback_type not in ("timeline", "trolley-timeline"):
                return
            if self._playback_id != timeline.get("id"):
                return
            self._timeline = timeline
            self.total_duration = timeline.get("duration", 0.0)
        logger.info("Hot-reloaded timeline %s during playback", timeline.get("id"))

    def seek(self, elapsed: float):
        """Seek to a specific elapsed time during playback."""
        with self._lock:
            if not self.playing:
                return
            elapsed = max(0.0, min(elapsed, self.total_duration))
            self._seek_offset = elapsed - (time.monotonic() - self._start_time)
            self.elapsed = elapsed

    # Order events at the same time deterministically. Safety-critical
    # commands run last so "enable → do things → stop" reads correctly.
    _TROLLEY_EVENT_ORDER = {
        "enable": 0, "dir": 1, "speed": 2,
        "position": 3, "step": 4,
        "stop": 5, "home": 6,
    }

    def _trolley_events(self):
        """Sorted (time, order, index, event) list for fast cursor traversal.
        The index is a tiebreaker so sorted() never falls through to
        comparing dicts (which is a TypeError on Python 3)."""
        tl = self._timeline or {}
        events = tl.get("events") or []
        items = []
        for i, ev in enumerate(events):
            if not isinstance(ev, dict):
                continue
            cmd = ev.get("command", "")
            if cmd not in self._TROLLEY_EVENT_ORDER:
                continue
            items.append(
                (float(ev.get("time", 0)),
                 self._TROLLEY_EVENT_ORDER[cmd],
                 i,
                 ev),
            )
        items.sort()
        return items

    def _fire_trolley_event(self, ev):
        """Send one /trolley/<command> OSC message per active device."""
        cmd = ev.get("command")
        value = ev.get("value")
        address = f"/trolley/{cmd}"
        # Commands without a value still need some OSC arg — pythonosc won't
        # send an empty payload. `0` is conventional.
        if cmd in ("stop", "home"):
            osc_value = 0
        elif cmd in ("enable", "dir", "step"):
            osc_value = int(value) if value is not None else 0
        else:  # speed, position
            osc_value = float(value) if value is not None else 0.0
        for device in self._devices:
            try:
                self.osc.send(
                    device["ip_address"],
                    device.get("osc_port", 9000),
                    address,
                    osc_value,
                )
            except Exception as e:
                logger.warning("Trolley event OSC send error to %s: %s",
                               device.get("id"), e)

    def _send_trolley_stop(self):
        """Fire /trolley/stop to every playback target. Used at timeline end."""
        for device in self._devices:
            try:
                self.osc.send(device["ip_address"],
                              device.get("osc_port", 9000),
                              "/trolley/stop", 0)
            except Exception as e:
                logger.warning("Trolley implicit-stop OSC error to %s: %s",
                               device.get("id"), e)

    def _clear_run_state(self) -> None:
        """Called from every run-loop finally so the UI reflects that the
        thread has exited, regardless of whether it finished cleanly or
        crashed. `_last_error` is preserved so the banner can still show it."""
        with self._lock:
            self.playing = False
            self.paused = False

    def _run_trolley_timeline(self):
        """Event-based trolley playback: fire each bang at its scheduled time."""
        try:
            interval = 1.0 / max(1, self.tick_rate)
            start_time = time.monotonic()
            self._start_time = start_time
            self._seek_offset = 0.0
            cursor = 0
            events = self._trolley_events()

            while not self._stop_event.is_set():
                self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                elapsed = time.monotonic() - start_time + self._seek_offset

                with self._lock:
                    if self.total_duration > 0 and elapsed >= self.total_duration:
                        # Implicit stop at end of a run, then wrap to t=0.
                        self._send_trolley_stop()
                        elapsed = elapsed % self.total_duration
                        self._seek_offset -= self.total_duration
                        cursor = 0
                    self.elapsed = elapsed

                    # Seek support: if elapsed moved backwards (seek() or loop wrap),
                    # re-find cursor.
                    if cursor > 0 and cursor <= len(events):
                        prev_ev_time = events[cursor - 1][0]
                        if elapsed < prev_ev_time:
                            cursor = 0

                    # Fire every event whose time has arrived.
                    while cursor < len(events) and events[cursor][0] <= elapsed:
                        self._fire_trolley_event(events[cursor][3])
                        cursor += 1

                next_tick = start_time + (int((time.monotonic() - start_time) / interval) + 1) * interval
                sleep_time = next_tick - time.monotonic()
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)

            # Exit path: make sure the trolley stops cleanly, whether we were
            # stopped externally or ran off the end.
            if not self._stop_event.is_set():
                self._send_trolley_stop()
        except Exception as e:
            logger.exception("playback _run_trolley_timeline crashed")
            self._last_error = f"trolley playback crashed: {e}"
        finally:
            self._clear_run_state()

    def _run_timeline(self):
        """Main timeline playback loop."""
        try:
            interval = 1.0 / self.tick_rate
            start_time = time.monotonic()
            self._start_time = start_time
            self._seek_offset = 0.0
            # Loop defaults to True so existing timelines keep their current
            # behaviour. Set `loop: false` in the timeline to stop at the end.
            loop_enabled = bool((self._timeline or {}).get("loop", True))

            while not self._stop_event.is_set():
                # Block while paused
                self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                elapsed = time.monotonic() - start_time + self._seek_offset

                with self._lock:
                    if elapsed >= self.total_duration:
                        if loop_enabled:
                            # Loop: reset time origin
                            elapsed = elapsed % self.total_duration
                            self._seek_offset -= self.total_duration
                        else:
                            # One-shot: snap to the final value and exit.
                            self.elapsed = self.total_duration
                            self._evaluate_and_send(self._timeline, self.total_duration)
                            break
                    self.elapsed = elapsed
                    self._evaluate_and_send(self._timeline, elapsed)

                # Sleep for next tick
                next_tick = start_time + (int((time.monotonic() - start_time) / interval) + 1) * interval
                sleep_time = next_tick - time.monotonic()
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)
        except Exception as e:
            logger.exception("playback _run_timeline crashed")
            self._last_error = f"timeline playback crashed: {e}"
        finally:
            self._clear_run_state()

    def _run_orchestration(self):
        """Main orchestration playback loop."""
        try:
            interval = 1.0 / self.tick_rate
            global_start = time.monotonic()
            steps = self._orchestration.get("steps", [])
            loop = self._orchestration.get("loop", False)

            while not self._stop_event.is_set():
                for step_idx, step in enumerate(steps):
                    if self._stop_event.is_set():
                        return

                    with self._lock:
                        self._current_step_index = step_idx

                    # Delay before
                    delay = step.get("delay_before", 0.0)
                    if delay > 0:
                        self._stop_event.wait(delay)
                        if self._stop_event.is_set():
                            return

                    # Get timeline and devices for this step
                    tl = self._resolved_timelines.get(step.get("timeline_id"))
                    if not tl:
                        continue

                    device_ids = step.get("device_ids", [])
                    step_devices = [
                        self._devices_map[did]
                        for did in device_ids
                        if did in self._devices_map
                    ]

                    with self._lock:
                        self._devices = step_devices

                    # Play the timeline
                    step_start = time.monotonic()
                    step_duration = tl.get("duration", 0.0)

                    while not self._stop_event.is_set():
                        step_elapsed = time.monotonic() - step_start
                        if step_elapsed >= step_duration:
                            break

                        with self._lock:
                            self.elapsed = time.monotonic() - global_start
                            self._evaluate_and_send(tl, step_elapsed)

                        next_tick = step_start + (int(step_elapsed / interval) + 1) * interval
                        sleep_time = next_tick - time.monotonic()
                        if sleep_time > 0:
                            self._stop_event.wait(sleep_time)

                if not loop:
                    break

            with self._lock:
                self.elapsed = self.total_duration
        except Exception as e:
            logger.exception("playback _run_orchestration crashed")
            self._last_error = f"orchestration playback crashed: {e}"
        finally:
            self._clear_run_state()

    def _evaluate_and_send(self, timeline: dict, current_time: float):
        """Evaluate lanes and send OSC to all active devices."""
        lanes = timeline.get("lanes", {})
        cap = self.output_cap / 100.0
        for lane_key in ("a", "b"):
            lane = lanes.get(lane_key, {})
            points = lane.get("points", [])
            value = evaluate_lane(points, current_time) * cap
            self.current_values[lane_key] = value

        for device in self._devices:
            try:
                ip = device["ip_address"]
                port = device.get("osc_port", 9000)
                # Vents are Peltier-based now: lane A → fan 1 PWM, lane B → fan 2 PWM.
                # Peltiers and target temperature are controlled via the panel,
                # not via timelines. Timeline plays fan curves only.
                self.osc.send(ip, port, "/vents/fan/1", self.current_values["a"])
                self.osc.send(ip, port, "/vents/fan/2", self.current_values["b"])
            except Exception as e:
                logger.warning("OSC send error to %s: %s", device.get("id"), e)
