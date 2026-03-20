"""Tests for the WebhookNotifier module."""

import json
import os
import time

import pytest
from unittest.mock import patch, MagicMock

from webhooks import WebhookNotifier


@pytest.fixture
def config_file(tmp_path):
    """Write a valid webhooks.json and return its path."""
    path = tmp_path / "webhooks.json"
    path.write_text(json.dumps({
        "webhooks": [
            {"url": "https://example.com/hook1", "events": ["start", "stop"]},
            {"url": "https://example.com/hook2", "events": ["crash"], "token": "secret"},
        ]
    }))
    return str(path)


# ── Loading ──────────────────────────────────────────────────────────


class TestLoad:
    def test_loads_valid_config(self, config_file):
        notifier = WebhookNotifier(config_file)
        assert len(notifier._hooks) == 2

    def test_missing_file_does_not_crash(self, tmp_path):
        notifier = WebhookNotifier(str(tmp_path / "nope.json"))
        assert notifier._hooks == []

    def test_malformed_json_does_not_crash(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json!!")
        notifier = WebhookNotifier(str(bad))
        assert notifier._hooks == []

    def test_wrong_structure_does_not_crash(self, tmp_path):
        wrong = tmp_path / "wrong.json"
        wrong.write_text(json.dumps({"other_key": 123}))
        notifier = WebhookNotifier(str(wrong))
        assert notifier._hooks == []

    def test_empty_webhooks_array(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"webhooks": []}))
        notifier = WebhookNotifier(str(empty))
        assert notifier._hooks == []


# ── Firing ───────────────────────────────────────────────────────────


class TestFire:
    def test_matching_events_are_queued(self, config_file):
        notifier = WebhookNotifier(config_file)
        # Drain the queue manually to check
        notifier._queue = MagicMock()
        notifier.fire("start")
        assert notifier._queue.put.call_count == 1
        hook, payload = notifier._queue.put.call_args[0][0]
        assert hook["url"] == "https://example.com/hook1"
        assert payload["event"] == "start"

    def test_non_matching_event_queues_nothing(self, config_file):
        notifier = WebhookNotifier(config_file)
        notifier._queue = MagicMock()
        notifier.fire("unknown_event")
        notifier._queue.put.assert_not_called()

    def test_fire_with_extra_data(self, config_file):
        notifier = WebhookNotifier(config_file)
        notifier._queue = MagicMock()
        notifier.fire("crash", {"error": "boom"})
        hook, payload = notifier._queue.put.call_args[0][0]
        assert payload["event"] == "crash"
        assert payload["error"] == "boom"

    def test_fire_never_raises(self, tmp_path):
        notifier = WebhookNotifier(str(tmp_path / "nope.json"))
        # Even with a broken _hooks list, fire must not raise
        notifier._hooks = None  # will cause iteration to fail
        notifier.fire("start")  # should not raise

    def test_fire_on_empty_notifier(self, tmp_path):
        notifier = WebhookNotifier(str(tmp_path / "nope.json"))
        notifier.fire("start")  # no hooks, no crash


# ── Posting (worker) ─────────────────────────────────────────────────


class TestPost:
    def test_successful_post(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook", "token": "tok"}
        payload = {"event": "start"}

        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier._post(hook, payload)
            mock_post.assert_called_once_with(
                "https://example.com/hook",
                json=payload,
                headers={"Authorization": "Bearer tok"},
                timeout=5,
            )

    def test_post_without_token(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook"}
        payload = {"event": "stop"}

        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier._post(hook, payload)
            mock_post.assert_called_once_with(
                "https://example.com/hook",
                json=payload,
                headers={},
                timeout=5,
            )

    def test_http_error_does_not_crash(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook"}

        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            notifier._post(hook, {"event": "start"})  # should not raise

    def test_connection_error_does_not_crash(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook"}

        import requests
        with patch("webhooks.requests.post", side_effect=requests.exceptions.ConnectionError):
            notifier._post(hook, {"event": "start"})  # should not raise

    def test_timeout_does_not_crash(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook"}

        import requests
        with patch("webhooks.requests.post", side_effect=requests.exceptions.Timeout):
            notifier._post(hook, {"event": "start"})  # should not raise

    def test_unexpected_exception_does_not_crash(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {"url": "https://example.com/hook"}

        with patch("webhooks.requests.post", side_effect=RuntimeError("weird")):
            notifier._post(hook, {"event": "start"})  # should not raise

    def test_missing_url_does_not_crash(self, config_file):
        notifier = WebhookNotifier(config_file)
        hook = {}  # no url key

        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier._post(hook, {"event": "start"})
            # Should use "<missing>" as fallback URL
            assert mock_post.call_args[0][0] == "<missing>"


# ── Integration: queue → worker → post ───────────────────────────────


class TestWorkerIntegration:
    def test_queued_item_gets_posted(self, config_file):
        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier = WebhookNotifier(config_file)
            notifier.fire("start")
            # Give the worker thread time to drain
            time.sleep(0.2)
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert call_kwargs[1]["json"]["event"] == "start"

    def test_multiple_events_all_posted(self, config_file):
        with patch("webhooks.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            notifier = WebhookNotifier(config_file)
            notifier.fire("start")
            notifier.fire("stop")
            notifier.fire("crash")
            time.sleep(0.3)
            # start→hook1, stop→hook1, crash→hook2 = 3 posts
            assert mock_post.call_count == 3
