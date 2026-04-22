"""OSC bridge: accept messages from an external source and fan out to devices.

An external OSC source (show controller, Max/Processing/TouchDesigner, etc.)
sends to the admin's bridge port. Each received message is:

  1. appended to a bounded ring buffer (last 500 events),
  2. routed to matching devices via OscSender,
  3. pushed to every subscribed SSE consumer.

Routing modes (chosen in Settings):
  - passthrough: every message forwarded unchanged to every device.
  - type-match: /vents/* → vents devices, /trolley/* → trolley devices,
    /sys/* → all devices. Anything else is logged but not forwarded.
  - none: events are logged but never forwarded (useful as a tap).
"""

import collections
import logging
import queue
import socketserver
import threading
import time
from typing import Any, Callable, Optional

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from engine.osc_sender import OscSender

logger = logging.getLogger(__name__)

RING_BUFFER_SIZE = 500
VALID_ROUTING = ("passthrough", "type-match", "none")


def _address_matches_type(address: str, device_type: str) -> bool:
    """Address-prefix → device-type routing under 'type-match' mode."""
    if address.startswith("/sys/"):
        return True
    if address.startswith("/vents/"):
        return device_type == "vents"
    if address.startswith("/trolley/"):
        return device_type == "trolley"
    # Unknown prefix under type-match: forward nowhere (logged with dropped).
    return False


class OscBridge:
    """Listen on a UDP port, fan out to devices, publish events on an SSE queue.

    Thread-safe for the public surface: start/stop/set_routing/get_events/
    subscribe can be called from any thread. Event fan-out runs on the OSC
    server's own thread.
    """

    def __init__(
        self,
        port: int = 9002,
        routing: str = "type-match",
        *,
        osc_sender: Optional[OscSender] = None,
        device_provider: Callable[[], list] = lambda: [],
    ):
        if routing not in VALID_ROUTING:
            raise ValueError(f"routing must be one of {VALID_ROUTING}")
        self._port = port
        self._routing = routing
        self._osc = osc_sender or OscSender()
        # Caller supplies a zero-arg function returning the current device list.
        # Keeping this as a callable means we don't have to rebuild the bridge
        # when devices are added/removed.
        self._device_provider = device_provider

        self._events: "collections.deque[dict]" = collections.deque(maxlen=RING_BUFFER_SIZE)
        self._subscribers: "list[queue.Queue]" = []
        self._lock = threading.Lock()

        self._server: Optional[BlockingOSCUDPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._error: Optional[str] = None

    # ── public surface ──────────────────────────────────────────────────

    @property
    def port(self) -> int:
        return self._port

    @property
    def routing(self) -> str:
        return self._routing

    @property
    def running(self) -> bool:
        return self._running

    @property
    def error(self) -> Optional[str]:
        return self._error

    def set_routing(self, routing: str) -> None:
        if routing not in VALID_ROUTING:
            raise ValueError(f"routing must be one of {VALID_ROUTING}")
        self._routing = routing

    def get_events(self) -> list:
        """Snapshot the ring buffer, oldest first."""
        with self._lock:
            return list(self._events)

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()

    def subscribe(self) -> "queue.Queue":
        """Return a queue onto which every new event is published. The caller
        is responsible for unsubscribing (see `unsubscribe`) — typically from
        an SSE generator's finally block."""
        q: "queue.Queue" = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue") -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def start(self) -> None:
        """(Re)bind the UDP listener. Idempotent: a running bridge is stopped
        and re-started against the current port / routing."""
        self.stop()
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle, needs_reply_address=True)
        try:
            socketserver.UDPServer.allow_reuse_address = True
            self._server = BlockingOSCUDPServer(("0.0.0.0", self._port), dispatcher)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name=f"osc-bridge-{self._port}",
                daemon=True,
            )
            self._thread.start()
            self._running = True
            self._error = None
            logger.info("OSC bridge listening on port %d (routing=%s)", self._port, self._routing)
        except OSError as e:
            self._running = False
            self._error = str(e)
            logger.error("Bridge failed to bind port %d: %s", self._port, e)

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as e:
                logger.debug("Bridge shutdown error: %s", e)
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._running = False

    def reconfigure(self, *, port: Optional[int] = None, routing: Optional[str] = None) -> None:
        """Apply new port / routing and restart if the port changed while running."""
        restart = False
        if port is not None and port != self._port:
            self._port = port
            restart = True
        if routing is not None and routing != self._routing:
            self.set_routing(routing)
        if restart and self._running:
            self.start()

    # ── internals ───────────────────────────────────────────────────────

    def _handle(self, client_address, address, *args) -> None:
        """Catch-all dispatcher handler: route + log + publish."""
        src_ip = client_address[0] if client_address else ""
        targets: list[str] = []
        dropped: Optional[str] = None

        if self._routing == "none":
            dropped = "routing=none"
        else:
            devices = list(self._device_provider())
            for device in devices:
                dev_ip = device.get("ip_address")
                if not dev_ip:
                    continue
                dev_type = device.get("type", "vents")
                if self._routing == "type-match" and not _address_matches_type(address, dev_type):
                    continue
                port = device.get("osc_port", 9000)
                try:
                    # python-osc's send_message accepts a single scalar or a list;
                    # pass *args verbatim so a bang with no args is still forwarded.
                    self._osc.send(dev_ip, port, address, _to_osc_value(args))
                    targets.append(device.get("id") or dev_ip)
                except Exception as e:
                    logger.warning("Bridge forward to %s failed: %s", dev_ip, e)
            if not targets and dropped is None and self._routing == "type-match":
                dropped = "no type-matching device"

        event = {
            "t": time.time(),
            "src": src_ip,
            "address": address,
            "args": list(args),
            "targets": targets,
        }
        if dropped:
            event["dropped"] = dropped

        with self._lock:
            self._events.append(event)
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Slow consumer — drop this one event rather than stall the
                # dispatcher. SSE frontend will just miss it.
                pass


def _to_osc_value(args: tuple) -> Any:
    """Flatten a pythonosc args tuple into what `send_message` expects.

    - No args → 0 (pythonosc refuses empty payloads).
    - Single arg → the scalar.
    - Multiple → the list (pythonosc handles lists natively).
    """
    if not args:
        return 0
    if len(args) == 1:
        return args[0]
    return list(args)
