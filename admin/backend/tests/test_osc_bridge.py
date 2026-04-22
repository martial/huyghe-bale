"""Unit tests for engine.osc_bridge — routing + ring buffer bounds.

No real UDP server is started; _handle is called directly with mocked
OscSender and a fake device list.
"""

from unittest.mock import MagicMock

import pytest

from engine.osc_bridge import OscBridge, RING_BUFFER_SIZE


def _devices():
    return [
        {"id": "vents-1",   "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"},
        {"id": "vents-2",   "ip_address": "10.0.0.2", "osc_port": 9000, "type": "vents"},
        {"id": "trolley-1", "ip_address": "10.0.0.3", "osc_port": 9000, "type": "trolley"},
        {"id": "no-ip",     "ip_address": "",          "osc_port": 9000, "type": "vents"},
    ]


def _make(routing="type-match"):
    sender = MagicMock()
    bridge = OscBridge(
        port=0,
        routing=routing,
        osc_sender=sender,
        device_provider=_devices,
    )
    return bridge, sender


# ── type-match routing ────────────────────────────────────────────────────


def test_type_match_forwards_vents_address_to_vents_only():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/vents/fan/1", 0.5)
    sent = [c.args for c in sender.send.call_args_list]
    # Two vents devices (no-ip dropped for empty ip). Trolley skipped.
    assert len(sent) == 2
    assert all(addr == "/vents/fan/1" for (_, _, addr, _) in sent)
    assert {ip for (ip, _, _, _) in sent} == {"10.0.0.1", "10.0.0.2"}


def test_type_match_forwards_trolley_address_to_trolley_only():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/trolley/position", 0.5)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    assert sent[0][0] == "10.0.0.3"


def test_type_match_forwards_sys_to_all():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/sys/ping", 9001)
    sent = [c.args for c in sender.send.call_args_list]
    # Three ips (no-ip still dropped)
    assert {ip for (ip, _, _, _) in sent} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}


def test_type_match_drops_unknown_prefix():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/show/scene", 1)
    sender.send.assert_not_called()
    evt = bridge.get_events()[-1]
    assert evt["dropped"] == "no type-matching device"
    assert evt["targets"] == []


# ── passthrough / none ────────────────────────────────────────────────────


def test_passthrough_forwards_to_every_device():
    bridge, sender = _make("passthrough")
    bridge._handle(("10.0.0.99", 50000), "/custom/thing", 1.0)
    sent = [c.args for c in sender.send.call_args_list]
    # 3 devices with IPs
    assert {ip for (ip, _, _, _) in sent} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}
    assert all(addr == "/custom/thing" for (_, _, addr, _) in sent)


def test_routing_none_logs_but_doesnt_forward():
    bridge, sender = _make("none")
    bridge._handle(("10.0.0.99", 50000), "/vents/fan/1", 0.5)
    sender.send.assert_not_called()
    evt = bridge.get_events()[-1]
    assert evt["dropped"] == "routing=none"


# ── arg flattening ────────────────────────────────────────────────────────


def test_no_args_forwards_zero_sentinel():
    bridge, sender = _make("passthrough")
    bridge._handle(("10.0.0.99", 50000), "/trolley/stop")
    # python-osc rejects empty payloads, so bangs are sent as 0
    for call in sender.send.call_args_list:
        assert call.args[-1] == 0


def test_multiple_args_forwarded_as_list():
    bridge, sender = _make("passthrough")
    bridge._handle(("10.0.0.99", 50000), "/custom/multi", 1, 2, 3)
    for call in sender.send.call_args_list:
        assert call.args[-1] == [1, 2, 3]


# ── ring buffer ───────────────────────────────────────────────────────────


def test_ring_buffer_bounded():
    bridge, _ = _make("none")
    for i in range(RING_BUFFER_SIZE + 50):
        bridge._handle(("1.2.3.4", 50000), "/x", i)
    events = bridge.get_events()
    assert len(events) == RING_BUFFER_SIZE
    # Oldest 50 got dropped; newest retained
    assert events[-1]["args"] == [RING_BUFFER_SIZE + 50 - 1]


def test_clear_empties_buffer():
    bridge, _ = _make("none")
    bridge._handle(("1.2.3.4", 50000), "/x", 1)
    assert len(bridge.get_events()) == 1
    bridge.clear_events()
    assert bridge.get_events() == []


# ── subscribers ───────────────────────────────────────────────────────────


def test_subscriber_receives_events():
    bridge, _ = _make("none")
    q = bridge.subscribe()
    bridge._handle(("1.2.3.4", 50000), "/x", 42)
    ev = q.get_nowait()
    assert ev["address"] == "/x"
    assert ev["args"] == [42]
    bridge.unsubscribe(q)


def test_unsubscribe_stops_delivery():
    bridge, _ = _make("none")
    q = bridge.subscribe()
    bridge.unsubscribe(q)
    bridge._handle(("1.2.3.4", 50000), "/x", 99)
    import queue as _q
    with pytest.raises(_q.Empty):
        q.get_nowait()


# ── reconfigure ───────────────────────────────────────────────────────────


def test_set_routing_validates():
    bridge, _ = _make("type-match")
    with pytest.raises(ValueError):
        bridge.set_routing("banana")


def test_reconfigure_applies_routing_immediately():
    bridge, sender = _make("type-match")
    bridge.reconfigure(routing="passthrough")
    bridge._handle(("10.0.0.99", 50000), "/anything", 1)
    assert sender.send.call_count == 3  # all 3 devices with ips
