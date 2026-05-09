"""Unit tests for engine.osc_bridge — routing + ring buffer bounds.

No real UDP server is started; _handle is called directly with mocked
OscSender and a fake device list.
"""

from unittest.mock import MagicMock

import pytest

from engine.osc_bridge import OscBridge, RING_BUFFER_SIZE


def _devices():
    return [
        {"id": "vents-1",   "name": "circadian.home",   "hardware_id": "vents_aaaa",   "ip_address": "10.0.0.1", "osc_port": 9000, "type": "vents"},
        {"id": "vents-2",   "name": "other-vents",      "hardware_id": "vents_bbbb",   "ip_address": "10.0.0.2", "osc_port": 9000, "type": "vents"},
        {"id": "trolley-1", "name": "screenclub.home",  "hardware_id": "trolley_cccc", "ip_address": "10.0.0.3", "osc_port": 9000, "type": "trolley"},
        {"id": "no-ip",     "name": "broken",           "hardware_id": "",             "ip_address": "",         "osc_port": 9000, "type": "vents"},
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


@pytest.mark.parametrize("address,value", [
    ("/vents/target", 18.0),       # legacy single-setpoint alias
    ("/vents/target/hot", 22.5),
    ("/vents/target/cold", 12.0),
])
def test_type_match_forwards_vents_target_subaddresses(address, value):
    """Regression: dual-setpoint addresses must route through type-match
    unchanged. Subpaths under /vents/target/ are still covered by the
    `/vents/` prefix rule."""
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), address, value)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 2  # both vents devices
    assert all(addr == address for (_, _, addr, _) in sent)
    assert all(arg == value for (_, _, _, arg) in sent)


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


# ── targeted dispatch: /to/<identifier>/<real-address> ───────────────────


def test_targeted_by_id():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/vents-2/vents/fan/1", 0.5)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    # Destination address is unwrapped; only the targeted device receives it
    assert sent[0] == ("10.0.0.2", 9000, "/vents/fan/1", 0.5)
    evt = bridge.get_events()[-1]
    assert evt["forwarded_as"] == "/vents/fan/1"
    assert evt["targets"] == ["vents-2"]
    assert "dropped" not in evt


def test_targeted_by_name():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/screenclub.home/trolley/home", 0)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    assert sent[0][0] == "10.0.0.3"
    assert sent[0][2] == "/trolley/home"


def test_targeted_by_ip():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/10.0.0.1/vents/target", 20)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    assert sent[0][0] == "10.0.0.1"
    assert sent[0][2] == "/vents/target"


def test_targeted_by_hardware_id():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/trolley_cccc/trolley/stop", 0)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    assert sent[0][0] == "10.0.0.3"


def test_targeted_unknown_identifier_drops():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/nonexistent/vents/fan/1", 0.5)
    sender.send.assert_not_called()
    evt = bridge.get_events()[-1]
    assert evt["dropped"] == "no device matching 'nonexistent'"


def test_targeted_overrides_routing_none():
    """Targeted dispatch must win even when the global routing is 'none'."""
    bridge, sender = _make("none")
    bridge._handle(("10.0.0.99", 50000), "/to/vents-1/vents/peltier/1", 1)
    assert sender.send.call_count == 1
    evt = bridge.get_events()[-1]
    assert "dropped" not in evt
    assert evt["targets"] == ["vents-1"]


def test_targeted_overrides_type_mismatch():
    """`/to/<vents-device>/trolley/anything` still reaches the vents device —
    the user asked for it explicitly, type-match is bypassed."""
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/to/vents-1/custom/address", 1)
    assert sender.send.call_count == 1
    assert sender.send.call_args.args[0] == "10.0.0.1"
    assert sender.send.call_args.args[2] == "/custom/address"


def test_targeted_malformed_no_trailing_address():
    bridge, sender = _make("type-match")
    # `/to/foo` has no destination address — parsed as not targeted, falls
    # through to normal routing. type-match doesn't recognise /to/ prefix so
    # it's dropped.
    bridge._handle(("10.0.0.99", 50000), "/to/foo", 1)
    sender.send.assert_not_called()
    evt = bridge.get_events()[-1]
    assert evt.get("dropped")


def test_targeted_empty_identifier():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "//vents/fan/1", 1)
    # Empty identifier — not a targeted address, falls back to normal routing
    # (and /vents/fan/1 fanout still works for the preceding "//" — actually
    # pythonosc treats the leading // as an empty first segment). We just
    # verify the bridge doesn't crash and nothing unexpected happens.
    evt = bridge.get_events()[-1]
    assert evt["address"] == "//vents/fan/1"


# ── rename flow: targeting tracks live device_provider changes ─────────────


def test_rename_takes_effect_on_next_message():
    """Mimicking the admin-rename flow: device_provider returns the current
    store contents on every call, so the bridge picks up a new name without
    needing a reconfigure."""
    state = [
        {"id": "d1", "name": "old-name", "ip_address": "10.0.0.9",
         "osc_port": 9000, "type": "vents"},
    ]
    sender = MagicMock()
    bridge = OscBridge(
        port=0,
        routing="type-match",
        osc_sender=sender,
        device_provider=lambda: state,
    )

    # Before rename
    bridge._handle(("1.1.1.1", 1000), "/to/old-name/vents/fan/1", 0.5)
    assert sender.send.call_count == 1

    # Simulate the admin PUT flow: the store's list_all() now returns the new name.
    state[0]["name"] = "new-name"

    # /to/old-name/… must now MISS
    sender.reset_mock()
    bridge._handle(("1.1.1.1", 1000), "/to/old-name/vents/fan/1", 0.5)
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "no device matching 'old-name'"

    # /to/new-name/… must HIT
    sender.reset_mock()
    bridge._handle(("1.1.1.1", 1000), "/to/new-name/vents/fan/1", 0.5)
    sender.send.assert_called_once()
    assert sender.send.call_args.args[0] == "10.0.0.9"


# ── /bridge/* macros: vents/off, trolley/off, position ────────────────────


def test_bridge_vents_off_fans_out_to_vents_only():
    """Disable auto + peltiers off + fans to 0 on every vents device. Trolleys
    receive nothing. The 4-message sequence is sent in order, mode=raw FIRST
    so the auto loop can't fight the subsequent peltier-off."""
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/vents/off")

    sent = [c.args for c in sender.send.call_args_list]
    # 2 vents (no-ip dropped) × 4 messages each = 8 sends. Trolley untouched.
    assert len(sent) == 8
    vents_ips = {ip for (ip, _, _, _) in sent}
    assert vents_ips == {"10.0.0.1", "10.0.0.2"}

    # Each device receives the same ordered sequence.
    for ip in ("10.0.0.1", "10.0.0.2"):
        per_device = [(addr, val) for (i, _, addr, val) in sent if i == ip]
        assert per_device == [
            ("/vents/mode", "raw"),
            ("/vents/peltier", 0),
            ("/vents/fan/1", 0.0),
            ("/vents/fan/2", 0.0),
        ]

    evt = bridge.get_events()[-1]
    assert evt["address"] == "/bridge/vents/off"
    assert set(evt["targets"]) == {"vents-1", "vents-2"}
    assert "dropped" not in evt
    assert len(evt["expanded"]) == 8


def test_bridge_vents_off_with_no_vents_devices_drops():
    sender = MagicMock()
    bridge = OscBridge(
        port=0, routing="type-match", osc_sender=sender,
        device_provider=lambda: [
            {"id": "trolley-only", "ip_address": "10.0.0.3",
             "osc_port": 9000, "type": "trolley"},
        ],
    )
    bridge._handle(("1.1.1.1", 1000), "/bridge/vents/off")
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "no vents devices"


def test_bridge_trolley_off_stops_trolleys_only():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/trolley/off")

    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1  # only one trolley in fixture
    ip, _, addr, val = sent[0]
    assert ip == "10.0.0.3"
    assert addr == "/trolley/stop"
    # Bang-with-no-args is sent as the 0 sentinel (python-osc refuses empty).
    assert val == 0

    evt = bridge.get_events()[-1]
    assert evt["targets"] == ["trolley-1"]
    assert "dropped" not in evt


def test_bridge_trolley_off_with_no_trolleys_drops():
    sender = MagicMock()
    bridge = OscBridge(
        port=0, routing="type-match", osc_sender=sender,
        device_provider=lambda: [
            {"id": "vents-only", "ip_address": "10.0.0.1",
             "osc_port": 9000, "type": "vents"},
        ],
    )
    bridge._handle(("1.1.1.1", 1000), "/bridge/trolley/off")
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "no trolley devices"


@pytest.mark.parametrize("incoming,expected", [
    (0.0, 0.1),
    (1.0, 0.9),
    (0.5, 0.5),
    (0.25, 0.3),
    # clamping
    (1.5, 0.9),
    (-0.2, 0.1),
])
def test_bridge_position_maps_value(incoming, expected):
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position", incoming)

    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    ip, _, addr, val = sent[0]
    assert ip == "10.0.0.3"
    assert addr == "/trolley/position"
    assert val == pytest.approx(expected)


def test_bridge_position_no_args_drops():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position")
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "missing or invalid position"


def test_bridge_position_non_numeric_drops():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position", "banana")
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "missing or invalid position"


def test_bridge_position_targeted_to_trolley_by_id():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position/trolley-1", 0.5)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 1
    assert sent[0] == ("10.0.0.3", 9000, "/trolley/position", pytest.approx(0.5))


def test_bridge_position_targeted_by_name_or_hardware_id():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position/screenclub.home", 1.0)
    assert sender.send.call_args.args[3] == pytest.approx(0.9)

    sender.reset_mock()
    bridge._handle(("10.0.0.99", 50000), "/bridge/position/trolley_cccc", 0.0)
    assert sender.send.call_args.args[3] == pytest.approx(0.1)


def test_bridge_position_targeted_at_vents_drops():
    """`/bridge/position/<vents-device>` must reject — type mismatch."""
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position/vents-1", 0.5)
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "target is not a trolley"


def test_bridge_position_unknown_identifier_drops():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/position/nope", 0.5)
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "no device matching 'nope'"


def test_bridge_unknown_command_drops():
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/bridge/whatever", 1)
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "unknown bridge command"


def test_bridge_macros_run_under_routing_none():
    """Bridge macros bypass routing mode entirely — same as /to/ targeting."""
    bridge, sender = _make("none")
    bridge._handle(("10.0.0.99", 50000), "/bridge/trolley/off")
    sender.send.assert_called_once()
    evt = bridge.get_events()[-1]
    assert evt["targets"] == ["trolley-1"]
    assert "dropped" not in evt


def test_normal_routing_unaffected_by_bridge_macros():
    """Regression: non-/bridge/ messages still route through type-match."""
    bridge, sender = _make("type-match")
    bridge._handle(("10.0.0.99", 50000), "/vents/fan/1", 0.5)
    sent = [c.args for c in sender.send.call_args_list]
    assert len(sent) == 2
    assert all(addr == "/vents/fan/1" for (_, _, addr, _) in sent)


def test_trailing_whitespace_defeats_exact_match():
    """Sanity check that _match_device is exact-match — proving the API's
    validation is load-bearing: if someone bypasses the API and stores a name
    with trailing whitespace, targeting will silently miss."""
    sender = MagicMock()
    bridge = OscBridge(
        port=0,
        routing="type-match",
        osc_sender=sender,
        device_provider=lambda: [
            {"id": "d1", "name": "vents ", "ip_address": "10.0.0.9",
             "osc_port": 9000, "type": "vents"},  # trailing space
        ],
    )

    bridge._handle(("1.1.1.1", 1000), "/to/vents/vents/fan/1", 0.5)
    sender.send.assert_not_called()
    assert bridge.get_events()[-1]["dropped"] == "no device matching 'vents'"
