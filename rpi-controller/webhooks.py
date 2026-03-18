"""Bulletproof webhook notifier — never crashes, never blocks."""

import json
import logging
import os
import queue
from threading import Thread

import requests

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webhooks.json")


class WebhookNotifier:
    def __init__(self, config_path=DEFAULT_PATH):
        self._hooks = []
        self._queue = queue.Queue()
        self._load(config_path)
        # Single daemon worker — dies with the process, no join needed
        Thread(target=self._worker, daemon=True).start()

    def _load(self, path):
        try:
            with open(path) as f:
                self._hooks = json.load(f).get("webhooks", [])
            logger.info("Loaded %d webhook(s) from %s", len(self._hooks), path)
        except FileNotFoundError:
            logger.warning("No webhook config at %s — webhooks disabled", path)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.error("Malformed webhook config %s: %s", path, e)
        except Exception as e:
            logger.error("Failed to load webhooks: %s", e)

    def fire(self, event, data=None):
        """Queue a webhook fire. Never raises, never blocks."""
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
                logger.info("Queued '%s' webhook to %d endpoint(s)", event, matched)
        except Exception as e:
            logger.warning("fire_webhook('%s') failed to queue: %s", event, e)

    def _worker(self):
        """Background loop — drains the queue forever."""
        while True:
            try:
                hook, payload = self._queue.get()
                self._post(hook, payload)
            except Exception as e:
                logger.warning("Webhook worker error: %s", e)

    def _post(self, hook, payload):
        url = hook.get("url", "<missing>")
        try:
            headers = {}
            token = hook.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code >= 400:
                logger.warning("Webhook %s returned HTTP %d", url, resp.status_code)
        except requests.exceptions.ConnectionError:
            logger.warning("Webhook %s unreachable (no network?)", url)
        except requests.exceptions.Timeout:
            logger.warning("Webhook %s timed out", url)
        except Exception as e:
            logger.warning("Webhook %s failed: %s", url, e)
