"""Thin OSC sender wrapper with lazy client creation."""

import threading
from typing import List, Optional, Union

from pythonosc.udp_client import SimpleUDPClient

Arg = Union[int, float, str, bool]


class OscSender:
    """Manages OSC UDP clients keyed by (ip, port).

    The cache dict is guarded by a lock because concurrent senders (playback
    engine tick thread, per-tab status pollers, the bridge listener) can race
    on the first insertion of a given (ip, port) key. Actual send_message
    calls remain lock-free — SimpleUDPClient is already safe to call from
    multiple threads.
    """

    def __init__(self):
        self._clients: dict[tuple[str, int], SimpleUDPClient] = {}
        self._lock = threading.Lock()

    def _get_client(self, ip: str, port: int) -> SimpleUDPClient:
        key = (ip, port)
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = SimpleUDPClient(ip, port)
                self._clients[key] = client
        return client

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

    def send_values(self, ip: str, port: int, address: str, values: Optional[List[Arg]] = None):
        """Send an OSC message with zero (bang) or more typed arguments.

        Args:
            values: Empty or None → no arguments. One element → single-arg message.
                Multiple elements → multiple OSC args (as a single list payload to pythonosc).
        """
        client = self._get_client(ip, port)
        if not values:
            client.send_message(address, None)
            return
        if len(values) == 1:
            client.send_message(address, values[0])
            return
        client.send_message(address, values)

    def send_zero(self, ip: str, port: int):
        """Halt a vents device: drop both fan PWMs to 0 and clear peltiers.
        The new vents controller uses /vents/* addresses; older /gpio/a,b Pis
        no longer exist in this codebase."""
        client = self._get_client(ip, port)
        client.send_message("/vents/fan/1", 0.0)
        client.send_message("/vents/fan/2", 0.0)
        client.send_message("/vents/peltier", 0)
