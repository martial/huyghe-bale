"""Tests for the OSC receiver /sys/pong parsing and /vents/status alarms."""

from engine.osc_receiver import OscReceiver


def _fresh_receiver():
    """Return the OscReceiver singleton with its dicts cleared.

    NB: we deliberately do not null `_instance` and recreate — other modules
    (api/vents_control, api/trolley_control) cache the singleton at import
    time, and replacing it would dangle those references across tests."""
    r = OscReceiver(port=19001)  # port arg ignored once singleton exists
    r.last_seen.clear()
    r.device_info.clear()
    r.trolley_status.clear()
    r.vents_status.clear()
    r._rpm_below_since.clear()
    r.active_alarms.clear()
    r.recent_alarms.clear()
    r.min_rpm_alarm = 500
    return r


def _vents_args(*, fan1=0.5, fan2=0.5, rpms=(800, 800, 800, 800),
                temp1=22.0, temp2=22.0, target=25.0, mode="auto", state="holding",
                max_temp=80.0, min_fan_pct=20.0, over_temp_fan_pct=100.0,
                max_fan_pct=100.0):
    """Helper: assemble a /vents/status arg tuple matching the Pi's contract."""
    return (
        float(temp1), float(temp2), float(fan1), float(fan2), 0,
        int(rpms[0]), int(rpms[1]), int(rpms[2]), int(rpms[3]),
        float(target), str(mode), str(state),
        float(max_temp), float(min_fan_pct), float(over_temp_fan_pct),
        float(max_fan_pct),
    )


class TestHandlePong:
    def test_legacy_pong_defaults_to_vents(self):
        r = _fresh_receiver()
        r._handle_pong(("192.168.1.42", 5000), "/sys/pong", "192.168.1.42")
        info = r.get_device_info("192.168.1.42")
        assert info == {"type": "vents", "hardware_id": ""}
        assert r.get_status("192.168.1.42") is True

    def test_extended_pong_records_type_and_id(self):
        r = _fresh_receiver()
        r._handle_pong(
            ("10.0.0.5", 5000), "/sys/pong",
            "10.0.0.5", "trolley", "trolley_a1b2c3d4",
        )
        info = r.get_device_info("10.0.0.5")
        assert info == {"type": "trolley", "hardware_id": "trolley_a1b2c3d4"}

    def test_vents_pong(self):
        r = _fresh_receiver()
        r._handle_pong(
            ("10.0.0.6", 5000), "/sys/pong",
            "10.0.0.6", "vents", "vents_deadbeef",
        )
        assert r.get_device_info("10.0.0.6") == {
            "type": "vents", "hardware_id": "vents_deadbeef",
        }

    def test_unknown_ip_returns_empty(self):
        r = _fresh_receiver()
        assert r.get_device_info("1.2.3.4") == {}

    def test_type_is_normalized_lowercase(self):
        r = _fresh_receiver()
        r._handle_pong(
            ("10.0.0.7", 5000), "/sys/pong",
            "10.0.0.7", "VENTS", "vents_x",
        )
        assert r.get_device_info("10.0.0.7")["type"] == "vents"


class TestHandleTrolleyStatus:
    def test_legacy_three_arg_payload(self):
        r = _fresh_receiver()
        r._handle_trolley_status(("10.0.0.8", 5000), "/trolley/status", 0.25, 0, 1)
        s = r.get_trolley_status("10.0.0.8")
        assert s["position"] == 0.25
        assert s["homed"] == 1
        assert s["state"] == "idle"        # default when not provided
        assert s["calibrated"] == 0        # default when not provided

    def test_extended_five_arg_payload(self):
        r = _fresh_receiver()
        r._handle_trolley_status(
            ("10.0.0.9", 5000), "/trolley/status",
            0.5, 0, 1, "calibrating", 0,
        )
        s = r.get_trolley_status("10.0.0.9")
        assert s["state"] == "calibrating"
        assert s["calibrated"] == 0

    def test_calibrated_true(self):
        r = _fresh_receiver()
        r._handle_trolley_status(
            ("10.0.0.10", 5000), "/trolley/status",
            0.0, 0, 1, "idle", 1,
        )
        assert r.get_trolley_status("10.0.0.10")["calibrated"] == 1


class TestHandleVentsStatus:
    def test_parses_full_payload(self):
        r = _fresh_receiver()
        r._handle_vents_status(
            ("10.1.0.1", 5000), "/vents/status",
            *_vents_args(min_fan_pct=33.0, over_temp_fan_pct=70.0, max_fan_pct=80.0),
        )
        s = r.vents_status["10.1.0.1"]
        assert s["min_fan_pct"] == 33.0
        assert s["max_fan_pct"] == 80.0
        assert s["over_temp_fan_pct"] == 70.0
        assert s["max_temp_c"] == 80.0
        # Alarm state is exposed via active_alarms / get_active_alarms,
        # not embedded in the per-device status snapshot.
        assert r.get_active_alarms("10.1.0.1") == []

    def test_legacy_15_arg_payload_still_parses_without_max_fan(self):
        r = _fresh_receiver()
        r._handle_vents_status(
            ("10.1.0.4", 5000), "/vents/status",
            22.0, 22.0, 0.5, 0.5, 0, 800, 800, 800, 800, 25.0, "auto", "holding",
            80.0, 20.0, 100.0,
        )
        s = r.vents_status["10.1.0.4"]
        assert s["min_fan_pct"] == 20.0
        assert "max_fan_pct" not in s

    def test_legacy_12_arg_payload_still_parses(self):
        r = _fresh_receiver()
        # Old firmware: no max_temp_c, no min/over fan keys
        r._handle_vents_status(
            ("10.1.0.2", 5000), "/vents/status",
            22.0, 22.0, 0.5, 0.5, 0, 800, 800, 800, 800, 25.0, "auto", "holding",
        )
        s = r.vents_status["10.1.0.2"]
        assert "max_temp_c" not in s
        assert "min_fan_pct" not in s
        assert "over_temp_fan_pct" not in s

    def test_negative_temp_decoded_as_none(self):
        r = _fresh_receiver()
        r._handle_vents_status(
            ("10.1.0.3", 5000), "/vents/status",
            *_vents_args(temp1=-1.0, temp2=22.0),
        )
        s = r.vents_status["10.1.0.3"]
        assert s["temp1_c"] is None
        assert s["temp2_c"] == 22.0


class TestRpmAlarmDetection:
    def test_below_threshold_alarms_only_after_debounce(self, monkeypatch):
        r = _fresh_receiver()
        r.set_min_rpm_alarm(500)
        # Anchor time so the 3-second debounce is deterministic
        t = [1000.0]
        monkeypatch.setattr("engine.osc_receiver.time.time", lambda: t[0])

        # Tick 1: fan commanded > 0, RPM = 200 < 500 — starts the timer, not yet active
        r._handle_vents_status(
            ("10.2.0.1", 5000), "/vents/status",
            *_vents_args(fan1=0.5, fan2=0.5, rpms=(200, 200, 800, 800)),
        )
        assert r.get_active_alarms("10.2.0.1") == []

        # Tick 2: 1.5s later — still under debounce
        t[0] = 1001.5
        r._handle_vents_status(
            ("10.2.0.1", 5000), "/vents/status",
            *_vents_args(fan1=0.5, fan2=0.5, rpms=(200, 200, 800, 800)),
        )
        assert r.get_active_alarms("10.2.0.1") == []

        # Tick 3: 3.5s after first below — now it should fire for ch 0 and 1
        t[0] = 1003.5
        r._handle_vents_status(
            ("10.2.0.1", 5000), "/vents/status",
            *_vents_args(fan1=0.5, fan2=0.5, rpms=(200, 200, 800, 800)),
        )
        assert r.get_active_alarms("10.2.0.1") == [0, 1]
        # Exactly two alarm events, no spam over the held below state
        events = [e for e in r.get_recent_alarms("10.2.0.1") if e["event"] == "alarm"]
        assert len(events) == 2
        assert {e["channel"] for e in events} == {0, 1}

    def test_recovery_clears_alarm(self, monkeypatch):
        r = _fresh_receiver()
        r.set_min_rpm_alarm(500)
        t = [1000.0]
        monkeypatch.setattr("engine.osc_receiver.time.time", lambda: t[0])

        # Drive ch 0 into alarm
        r._handle_vents_status(("10.2.0.2", 5000), "/vents/status",
                               *_vents_args(rpms=(100, 800, 800, 800)))
        t[0] += 4.0
        r._handle_vents_status(("10.2.0.2", 5000), "/vents/status",
                               *_vents_args(rpms=(100, 800, 800, 800)))
        assert 0 in r.get_active_alarms("10.2.0.2")

        # RPM recovers — should clear in the same tick (no debounce on recovery)
        t[0] += 0.5
        r._handle_vents_status(("10.2.0.2", 5000), "/vents/status",
                               *_vents_args(rpms=(900, 800, 800, 800)))
        assert 0 not in r.get_active_alarms("10.2.0.2")

        # Exactly one ALARM and one OK transition
        events = list(r.get_recent_alarms("10.2.0.2"))
        kinds = [e["event"] for e in events if e["channel"] == 0]
        assert kinds == ["alarm", "ok"]

    def test_zero_command_does_not_alarm(self, monkeypatch):
        r = _fresh_receiver()
        r.set_min_rpm_alarm(500)
        t = [1000.0]
        monkeypatch.setattr("engine.osc_receiver.time.time", lambda: t[0])

        # Fan idle → no alarm even though RPM is 0
        r._handle_vents_status(("10.2.0.3", 5000), "/vents/status",
                               *_vents_args(fan1=0.0, fan2=0.0, rpms=(0, 0, 0, 0)))
        t[0] += 5.0
        r._handle_vents_status(("10.2.0.3", 5000), "/vents/status",
                               *_vents_args(fan1=0.0, fan2=0.0, rpms=(0, 0, 0, 0)))
        assert r.get_active_alarms("10.2.0.3") == []

    def test_threshold_zero_disables_alarm(self, monkeypatch):
        r = _fresh_receiver()
        r.set_min_rpm_alarm(0)  # disabled
        t = [1000.0]
        monkeypatch.setattr("engine.osc_receiver.time.time", lambda: t[0])

        r._handle_vents_status(("10.2.0.4", 5000), "/vents/status",
                               *_vents_args(fan1=0.5, rpms=(0, 0, 0, 0)))
        t[0] += 10.0
        r._handle_vents_status(("10.2.0.4", 5000), "/vents/status",
                               *_vents_args(fan1=0.5, rpms=(0, 0, 0, 0)))
        assert r.get_active_alarms("10.2.0.4") == []

    def test_set_min_rpm_alarm_updates_threshold(self):
        r = _fresh_receiver()
        r.set_min_rpm_alarm(750)
        assert r.min_rpm_alarm == 750
        r.set_min_rpm_alarm("not a number")
        assert r.min_rpm_alarm == 750  # unchanged on bad input
        r.set_min_rpm_alarm(-50)
        assert r.min_rpm_alarm == 0    # negative clamped to 0
