"""Thin OSC sender wrapper with lazy client creation."""

from pythonosc.udp_client import SimpleUDPClient


class OscSender:
    """Manages OSC UDP clients keyed by (ip, port)."""

    def __init__(self):
        self._clients: dict[tuple[str, int], SimpleUDPClient] = {}

    def _get_client(self, ip: str, port: int) -> SimpleUDPClient:
        key = (ip, port)
        if key not in self._clients:
            self._clients[key] = SimpleUDPClient(ip, port)
        return self._clients[key]

    def send(self, ip: str, port: int, address: str, value: float):
        """Send an OSC message.

        Args:
            ip: Target IP address.
            port: Target UDP port.
            address: OSC address (e.g., /gpio/a).
            value: Float value to send.
        """
        client = self._get_client(ip, port)
        client.send_message(address, value)

    def send_zero(self, ip: str, port: int):
        """Halt a vents device: drop both fan PWMs to 0 and clear peltiers.
        The new vents controller uses /vents/* addresses; older /gpio/a,b Pis
        no longer exist in this codebase."""
        client = self._get_client(ip, port)
        client.send_message("/vents/fan/1", 0.0)
        client.send_message("/vents/fan/2", 0.0)
        client.send_message("/vents/peltier", 0)
