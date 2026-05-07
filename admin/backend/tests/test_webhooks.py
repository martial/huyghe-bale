"""Tests for engine.webhooks — admin-side webhook notifier and status watcher."""

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from engine.webhooks import WebhookNotifier


@contextmanager
def mock_urlopen():
    """Patch urllib.request.urlopen with a context-manager-friendly mock and
    yield the underlying mock so tests can inspect calls."""
    captured: list = []

    @contextmanager
    def _fake_urlopen(req, timeout=None):
        captured.append({
            "url": req.full_url,
            "method": req.get_method(),
            "headers": dict(req.headers),
            "body": req.data.decode() if req.data else None,
            "timeout": timeout,
        })
        resp = MagicMock()
        resp.status = 200
        yield resp

    with patch("engine.webhooks.urllib.request.urlopen", _fake_urlopen):
        yield captured


@pytest.fixture
def hooks_file(tmp_path):
    """Write a webhooks.json with one hook listening for status_change."""
    cfg = {
        "webhooks": [
            {"url": "https://example.test/hook", "events": ["status_change"]},
        ]
    }
    (tmp_path / "webhooks.json").write_text(json.dumps(cfg))
    return tmp_path


@pytest.fixture
def notifier(hooks_file):
    return WebhookNotifier(str(hooks_file))


# ── load / fire ─────────────────────────────────────────────────────────────


class TestLoad:
    def test_missing_file_disables_silently(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        assert n._hooks == []
        # fire() must not raise
        assert n.fire("status_change", {"x": 1}) == 0

    def test_malformed_json_disables_silently(self, tmp_path):
        (tmp_path / "webhooks.json").write_text("{ not json")
        n = WebhookNotifier(str(tmp_path))
        assert n._hooks == []

    def test_loads_hook_list(self, notifier):
        assert len(notifier._hooks) == 1
        assert notifier._hooks[0]["url"] == "https://example.test/hook"


class TestFire:
    def test_matching_event_returns_one(self, notifier):
        assert notifier.fire("status_change", {"foo": "bar"}) == 1

    def test_post_emits_correct_wire_shape(self, notifier):
        with mock_urlopen() as captured:
            notifier._post(notifier._hooks[0],
                           {"event": "status_change", "foo": "bar"})
        assert len(captured) == 1
        call = captured[0]
        assert call["url"] == "https://example.test/hook"
        assert call["method"] == "POST"
        assert call["timeout"] == 5
        assert json.loads(call["body"]) == {"event": "status_change", "foo": "bar"}
        # urllib lowercases header keys when storing on Request.
        assert call["headers"]["Content-type"] == "application/json"

    def test_unmatched_event_returns_zero(self, notifier):
        assert notifier.fire("never_fires", {}) == 0

    def test_token_becomes_bearer_header(self, tmp_path):
        cfg = {"webhooks": [
            {"url": "https://x", "token": "abc123", "events": ["e"]},
        ]}
        (tmp_path / "webhooks.json").write_text(json.dumps(cfg))
        n = WebhookNotifier(str(tmp_path))
        with mock_urlopen() as captured:
            n._post(n._hooks[0], {"event": "e"})
        assert captured[0]["headers"]["Authorization"] == "Bearer abc123"

    def test_token_already_prefixed_not_doubled(self, tmp_path):
        cfg = {"webhooks": [
            {"url": "https://x", "token": "Bearer keepme", "events": ["e"]},
        ]}
        (tmp_path / "webhooks.json").write_text(json.dumps(cfg))
        n = WebhookNotifier(str(tmp_path))
        with mock_urlopen() as captured:
            n._post(n._hooks[0], {"event": "e"})
        assert captured[0]["headers"]["Authorization"] == "Bearer keepme"

    def test_post_failure_does_not_propagate(self, notifier):
        with patch("engine.webhooks.urllib.request.urlopen",
                   side_effect=Exception("network down")):
            # Should swallow the exception silently.
            notifier._post(notifier._hooks[0], {"event": "status_change"})


# ── status watcher transition logic ─────────────────────────────────────────


def _make_receiver(online_ips):
    """Receiver mock whose get_status() returns True for the given IPs."""
    rec = MagicMock()
    rec.get_status.side_effect = lambda ip, timeout=6.0: ip in online_ips
    rec.get_vents_status.return_value = {"temp1_c": 24.5, "mode": "auto"}
    rec.get_trolley_status.return_value = {"position": 0.5, "homed": 1}
    return rec


def _make_store(devices):
    s = MagicMock()
    s.list_all.return_value = devices
    return s


class TestStatusWatcher:
    """Drive _tick() directly; the daemon thread is excercised separately
    via start_status_watcher (smoke test below)."""

    def test_first_observation_does_not_fire(self, notifier):
        device = {"id": "dev_1", "name": "Vent 1", "ip_address": "10.0.0.5",
                  "osc_port": 9000, "type": "vents"}
        prev: dict = {}
        with patch.object(notifier, "fire") as mock_fire:
            notifier._tick(_make_receiver({"10.0.0.5"}),
                           _make_store([device]), prev, timeout_s=6.0)
            mock_fire.assert_not_called()
        assert prev == {"dev_1": "online"}

    def test_online_to_offline_fires(self, notifier):
        device = {"id": "dev_1", "name": "Vent 1", "ip_address": "10.0.0.5",
                  "osc_port": 9000, "type": "vents", "hardware_id": "vents_abcd1234"}
        prev: dict = {"dev_1": "online"}
        rec = _make_receiver(set())  # nobody online now
        with patch.object(notifier, "fire") as mock_fire:
            notifier._tick(rec, _make_store([device]), prev, timeout_s=6.0)
            mock_fire.assert_called_once()
            event, payload = mock_fire.call_args.args
            assert event == "status_change"
            assert payload["status"] == "offline"
            assert payload["previous"] == "online"
            assert payload["device"]["name"] == "Vent 1"
            assert payload["device"]["ip_address"] == "10.0.0.5"
            assert payload["device"]["hardware_id"] == "vents_abcd1234"
            assert "controller_status" in payload
        assert prev == {"dev_1": "offline"}

    def test_offline_to_online_fires(self, notifier):
        device = {"id": "dev_1", "name": "T0", "ip_address": "10.0.0.6",
                  "osc_port": 9000, "type": "trolley"}
        prev: dict = {"dev_1": "offline"}
        rec = _make_receiver({"10.0.0.6"})
        with patch.object(notifier, "fire") as mock_fire:
            notifier._tick(rec, _make_store([device]), prev, timeout_s=6.0)
            event, payload = mock_fire.call_args.args
            assert payload["status"] == "online"
            assert payload["previous"] == "offline"
            # Trolley devices include trolley_status under controller_status.
            assert payload["controller_status"] == {"position": 0.5, "homed": 1}

    def test_no_change_does_not_fire(self, notifier):
        device = {"id": "dev_1", "name": "Vent 1", "ip_address": "10.0.0.5",
                  "osc_port": 9000, "type": "vents"}
        prev: dict = {"dev_1": "online"}
        with patch.object(notifier, "fire") as mock_fire:
            notifier._tick(_make_receiver({"10.0.0.5"}),
                           _make_store([device]), prev, timeout_s=6.0)
            mock_fire.assert_not_called()

    def test_deleted_device_drops_from_prev(self, notifier):
        device = {"id": "dev_keep", "name": "Keep", "ip_address": "10.0.0.5",
                  "osc_port": 9000, "type": "vents"}
        prev: dict = {"dev_keep": "online", "dev_gone": "offline"}
        notifier._tick(_make_receiver({"10.0.0.5"}),
                       _make_store([device]), prev, timeout_s=6.0)
        assert "dev_gone" not in prev
        assert prev["dev_keep"] == "online"

    def test_devices_without_ip_are_skipped(self, notifier):
        device = {"id": "dev_no_ip", "name": "Unconfigured",
                  "ip_address": "", "osc_port": 9000, "type": "vents"}
        prev: dict = {}
        with patch.object(notifier, "fire") as mock_fire:
            notifier._tick(_make_receiver(set()),
                           _make_store([device]), prev, timeout_s=6.0)
            mock_fire.assert_not_called()
        assert prev == {}


# ── reload ──────────────────────────────────────────────────────────────────


class TestReload:
    def test_reload_picks_up_new_hooks(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        assert n._hooks == []
        cfg = {"webhooks": [{"url": "https://x", "events": ["e"]}]}
        (tmp_path / "webhooks.json").write_text(json.dumps(cfg))
        n.reload()
        assert len(n._hooks) == 1


# ── extra hooks (Settings-page-managed) ─────────────────────────────────────


class TestExtraHooks:
    def test_set_extra_hooks_adds_runtime_entry(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([{"url": "https://settings", "events": ["status_change"]}])
        assert len(n._hooks) == 1
        assert n._hooks[0]["url"] == "https://settings"

    def test_extra_and_file_hooks_both_active(self, tmp_path):
        cfg = {"webhooks": [{"url": "https://from-file", "events": ["status_change"]}]}
        (tmp_path / "webhooks.json").write_text(json.dumps(cfg))
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([{"url": "https://from-settings", "events": ["status_change"]}])
        urls = [h["url"] for h in n._hooks]
        assert "https://from-file" in urls
        assert "https://from-settings" in urls

    def test_set_extra_hooks_replaces_previous(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([{"url": "https://old", "events": ["status_change"]}])
        n.set_extra_hooks([{"url": "https://new", "events": ["status_change"]}])
        urls = [h["url"] for h in n._hooks]
        assert urls == ["https://new"]

    def test_set_extra_hooks_drops_entries_without_url(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([
            {"url": "https://valid", "events": ["status_change"]},
            {"url": "", "events": ["status_change"]},
            None,
            {"events": ["status_change"]},  # missing url key
        ])
        assert len(n._hooks) == 1
        assert n._hooks[0]["url"] == "https://valid"

    def test_empty_list_clears_extra_hooks(self, tmp_path):
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([{"url": "https://x", "events": ["status_change"]}])
        n.set_extra_hooks([])
        assert n._hooks == []

    def test_fire_routes_to_extra_hooks(self, tmp_path):
        """Extra hooks must dispatch through the same fire() pipeline as
        file-based hooks. Test the queueing without awaiting the daemon
        worker — race-free and avoids real DNS lookups."""
        n = WebhookNotifier(str(tmp_path))
        n.set_extra_hooks([{"url": "https://x", "events": ["status_change"]}])
        before = n._queue.qsize()
        assert n.fire("status_change", {"foo": "bar"}) == 1
        # The fire() call must have enqueued exactly one item destined for
        # the extra hook. Drain it synchronously here so the daemon worker
        # has nothing left to attempt with real urlopen.
        try:
            hook, payload = n._queue.get(timeout=0.5)
        except Exception:
            pytest.fail("fire() did not enqueue the expected item")
        assert hook["url"] == "https://x"
        assert payload == {"event": "status_change", "foo": "bar"}
        assert n._queue.qsize() == before
