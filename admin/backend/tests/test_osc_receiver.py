"""Tests for the OSC receiver /sys/pong parsing."""

from engine.osc_receiver import OscReceiver


def _fresh_receiver():
    # Reset singleton so each test gets clean state
    OscReceiver._instance = None
    return OscReceiver(port=19001)  # unusual port, we never .start() here


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
