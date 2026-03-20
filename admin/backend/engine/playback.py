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
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_timeline, daemon=True)
        self._thread.start()
        logger.info("Playback started: timeline %s to %d device(s)", timeline.get("id"), len(devices))

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
        """Stop playback and zero all outputs."""
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused so thread can exit
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            self.paused = False
            # Zero all devices
            for device in self._devices:
                try:
                    self.osc.send_zero(device["ip_address"], device.get("osc_port", 9000))
                except Exception as e:
                    logger.warning("Failed to zero device %s: %s", device.get("id"), e)

            self.playing = False
            self.elapsed = 0.0
            self.current_values = {"a": 0.0, "b": 0.0}
            self._timeline = None
            self._orchestration = None
            self._devices = []
            self._playback_type = None
            self._playback_id = None

        logger.info("Playback stopped")

    def seek(self, elapsed: float):
        """Seek to a specific elapsed time during playback."""
        with self._lock:
            if not self.playing:
                return
            elapsed = max(0.0, min(elapsed, self.total_duration))
            self._seek_offset = elapsed - (time.monotonic() - self._start_time)
            self.elapsed = elapsed

    def _run_timeline(self):
        """Main timeline playback loop."""
        interval = 1.0 / self.tick_rate
        start_time = time.monotonic()
        self._start_time = start_time
        self._seek_offset = 0.0

        while not self._stop_event.is_set():
            # Block while paused
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            elapsed = time.monotonic() - start_time + self._seek_offset

            with self._lock:
                if elapsed >= self.total_duration:
                    self.elapsed = self.total_duration
                    break
                self.elapsed = elapsed
                self._evaluate_and_send(self._timeline, elapsed)

            # Sleep for next tick
            next_tick = start_time + (int((time.monotonic() - start_time) / interval) + 1) * interval
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        with self._lock:
            # Send final values
            if self._timeline and not self._stop_event.is_set():
                self._evaluate_and_send(self._timeline, self.total_duration)
            self.playing = False

    def _run_orchestration(self):
        """Main orchestration playback loop."""
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
            self.playing = False

    def _evaluate_and_send(self, timeline: dict, current_time: float):
        """Evaluate lanes and send OSC to all active devices."""
        lanes = timeline.get("lanes", {})
        for lane_key in ("a", "b"):
            lane = lanes.get(lane_key, {})
            points = lane.get("points", [])
            value = evaluate_lane(points, current_time)
            self.current_values[lane_key] = value

        for device in self._devices:
            try:
                ip = device["ip_address"]
                port = device.get("osc_port", 9000)
                self.osc.send(ip, port, "/gpio/a", self.current_values["a"])
                self.osc.send(ip, port, "/gpio/b", self.current_values["b"])
            except Exception as e:
                logger.warning("OSC send error to %s: %s", device.get("id"), e)
