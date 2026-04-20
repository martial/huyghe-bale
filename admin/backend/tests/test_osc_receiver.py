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
