"""Async webhook notifier for the admin backend.

Mirrors `rpi-controller/webhooks.py`: file-based config, single daemon
worker, non-blocking `fire()`. Plus a status-change watcher that polls the
OscReceiver and fires `status_change` events on online/offline transitions,
and a periodic snapshot watcher that fires `device_snapshot` on a configurable
interval for downstream stats collection.

Config file: `<DATA_DIR>/webhooks.json` (gitignored). Schema:

    {
      "webhooks": [
        {"url": "https://...", "events": ["status_change"]},
        {"url": "https://...", "token": "Bearer ...", "events": ["status_change"]}
      ]
    }

When a device transitions online <-> offline the notifier POSTs:

    {
      "event": "status_change",
      "device": {id, name, ip_address, osc_port, type, hardware_id},
      "status": "online" | "offline",
      "previous": "online" | "offline",
      "controller_status": <last receiver snapshot, may be {}>,
      "timestamp": <unix seconds>
    }

On each snapshot tick the notifier POSTs:

    {
      "event": "device_snapshot",
      "devices": [
        {"device": {...}, "status": "online"|"offline", "controller_status": {...}},
        ...
      ],
      "timestamp": <unix seconds>
    }
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

WEBHOOKS_FILENAME = "webhooks.json"


class WebhookNotifier:
    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        # File-based hooks (loaded from webhooks.json — power-user escape hatch).
        self._file_hooks: list = []
        # Extra hooks injected at runtime (from settings.json — UI-managed).
        self._extra_hooks: list = []
        self._hooks_lock = threading.Lock()
        self._queue: "queue.Queue" = queue.Queue()
        self._load()
        threading.Thread(
            target=self._worker, name="webhooks-worker", daemon=True
        ).start()
        self._watcher_started = False
        self._watcher_stop = threading.Event()
        self._stats_watcher_started = False
        self._stats_watcher_stop = threading.Event()

    @property
    def config_path(self) -> str:
        return os.path.join(self._data_dir, WEBHOOKS_FILENAME)

    def _load(self):
        path = self.config_path
        try:
            with open(path) as f:
                doc = json.load(f)
            with self._hooks_lock:
                self._file_hooks = doc.get("webhooks", []) or []
            logger.info("Admin webhooks: loaded %d hook(s) from %s",
                        len(self._file_hooks), path)
        except FileNotFoundError:
            with self._hooks_lock:
                self._file_hooks = []
            logger.info("Admin webhooks: no config at %s — webhooks disabled", path)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            with self._hooks_lock:
                self._file_hooks = []
            logger.error("Admin webhooks: malformed %s: %s", path, e)
        except Exception as e:
            with self._hooks_lock:
                self._file_hooks = []
            logger.error("Admin webhooks: failed to load %s: %s", path, e)

    def reload(self):
        """Re-read the file-based config. Safe to call from a settings hook."""
        self._load()

    def set_extra_hooks(self, hooks: list):
        """Replace runtime extra hooks (typically the single Settings-page-managed
        entry). Pass `[]` to clear. File-based hooks are unaffected."""
        with self._hooks_lock:
            self._extra_hooks = [h for h in (hooks or []) if h and h.get("url")]
        logger.info("Admin webhooks: %d extra hook(s) set from runtime",
                    len(self._extra_hooks))

    @property
    def _hooks(self):
        """All active hooks (file + extra). Read-only — set via _load() / set_extra_hooks()."""
        with self._hooks_lock:
            return list(self._file_hooks) + list(self._extra_hooks)

    def fire(self, event: str, data: Optional[dict] = None) -> int:
        """Queue an event for delivery. Returns number of hooks matched.
        Never raises, never blocks."""
        try:
            payload = {"event": event}
            if data:
                payload.update(data)
            matched = 0
            for hook in self._hooks:
                if event in hook.get("events", []):
                    self._queue.put((hook, payload))
                    matched += 1
            if matched:
                logger.info("Webhook '%s' queued for %d endpoint(s)", event, matched)
            return matched
        except Exception as e:
            logger.warning("Webhook fire('%s') failed to queue: %s", event, e)
            return 0

    # --- worker -----------------------------------------------------------

    def _worker(self):
        while True:
            try:
                hook, payload = self._queue.get()
                self._post(hook, payload)
            except Exception as e:
                logger.warning("Webhook worker error: %s", e)

    def _post(self, hook: dict, payload: dict):
        url = hook.get("url", "<missing>")
        try:
            headers = {"Content-Type": "application/json"}
            token = hook.get("token")
            if token:
                t = str(token).strip()
                headers["Authorization"] = t if t.lower().startswith("bearer ") else f"Bearer {t}"
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status >= 400:
                    logger.warning("Webhook %s returned HTTP %d", url, resp.status)
        except urllib.error.HTTPError as e:
            logger.warning("Webhook %s returned HTTP %d", url, e.code)
        except urllib.error.URLError as e:
            logger.warning("Webhook %s unreachable: %s", url, e.reason)
        except TimeoutError:
            logger.warning("Webhook %s timed out", url)
        except Exception as e:
            logger.warning("Webhook %s failed: %s", url, e)

    # --- status-change watcher --------------------------------------------

    def start_status_watcher(self, receiver, device_store, *,
                             interval_s: float = 1.0, timeout_s: float = 6.0):
        """Spawn a daemon thread that fires `status_change` webhooks on
        online/offline transitions.

        Idempotent — calling twice is a no-op.
        """
        if self._watcher_started:
            return
        self._watcher_started = True
        self._watcher_stop.clear()

        def _run():
            prev: dict[str, str] = {}
            while not self._watcher_stop.is_set():
                try:
                    self._tick(receiver, device_store, prev, timeout_s)
                except Exception as e:
                    logger.debug("status watcher tick error: %s", e)
                self._watcher_stop.wait(interval_s)

        threading.Thread(
            target=_run, name="webhooks-status-watcher", daemon=True
        ).start()
        logger.info(
            "Admin webhooks: status watcher started (interval=%.1fs, timeout=%.1fs)",
            interval_s, timeout_s,
        )

    def stop_status_watcher(self):
        self._watcher_stop.set()
        self._watcher_started = False

    def _tick(self, receiver, device_store, prev: dict, timeout_s: float):
        current_ids = set()
        for device in device_store.list_all():
            did = device.get("id")
            ip = device.get("ip_address")
            if not did or not ip:
                continue
            current_ids.add(did)
            status = "online" if receiver.get_status(ip, timeout=timeout_s) else "offline"
            previous = prev.get(did)
            if previous is None:
                # First observation for this device — capture without firing.
                prev[did] = status
                continue
            if previous == status:
                continue
            prev[did] = status
            self.fire(
                "status_change",
                self._status_change_payload(device, status, previous, receiver),
            )
        # Drop devices that have been deleted so prev doesn't leak.
        for stale in set(prev) - current_ids:
            prev.pop(stale, None)

    def _device_snapshot(self, device: dict, receiver) -> tuple[dict, dict]:
        """Return (device_dict, controller_status) for one device — shared by
        status-change and periodic-snapshot payload builders."""
        ip = device.get("ip_address")
        controller_status: dict = {}
        device_type = (device.get("type") or "").strip().lower()
        if device_type == "vents" and hasattr(receiver, "get_vents_status"):
            controller_status = receiver.get_vents_status(ip)
        elif device_type == "trolley" and hasattr(receiver, "get_trolley_status"):
            controller_status = receiver.get_trolley_status(ip)
        return (
            {
                "id": device.get("id"),
                "name": device.get("name"),
                "ip_address": ip,
                "osc_port": device.get("osc_port"),
                "type": device.get("type"),
                "hardware_id": device.get("hardware_id"),
            },
            controller_status,
        )

    def _status_change_payload(self, device: dict, status: str, previous: str, receiver) -> dict:
        device_dict, controller_status = self._device_snapshot(device, receiver)
        return {
            "device": device_dict,
            "status": status,
            "previous": previous,
            "controller_status": controller_status,
            "timestamp": time.time(),
        }

    # --- periodic snapshot watcher ----------------------------------------

    def start_stats_watcher(self, receiver, device_store, *,
                            get_interval_s, timeout_s: float = 6.0):
        """Spawn a daemon thread that fires `device_snapshot` webhooks every
        `get_interval_s()` seconds. The interval is read on each tick so
        live changes via the settings API take effect on the next loop.

        Idempotent — calling twice is a no-op.
        """
        if self._stats_watcher_started:
            return
        self._stats_watcher_started = True
        self._stats_watcher_stop.clear()

        def _run():
            while not self._stats_watcher_stop.is_set():
                try:
                    payload = self._device_snapshot_payload(
                        device_store, receiver, timeout_s,
                    )
                    self.fire("device_snapshot", payload)
                except Exception as e:
                    logger.debug("stats watcher tick error: %s", e)
                try:
                    interval = int(get_interval_s())
                except Exception:
                    interval = 60
                interval = max(10, min(3600, interval))
                self._stats_watcher_stop.wait(interval)

        threading.Thread(
            target=_run, name="webhooks-stats-watcher", daemon=True
        ).start()
        logger.info("Admin webhooks: stats watcher started")

    def stop_stats_watcher(self):
        self._stats_watcher_stop.set()
        self._stats_watcher_started = False

    def _device_snapshot_payload(self, device_store, receiver, timeout_s: float) -> dict:
        devices = []
        for device in device_store.list_all():
            ip = device.get("ip_address")
            if not ip:
                continue
            device_dict, controller_status = self._device_snapshot(device, receiver)
            devices.append({
                "device": device_dict,
                "status": "online" if receiver.get_status(ip, timeout=timeout_s) else "offline",
                "controller_status": controller_status,
            })
        return {"devices": devices, "timestamp": time.time()}
