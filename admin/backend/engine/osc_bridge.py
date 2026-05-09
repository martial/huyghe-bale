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

# Bridge-side macro addresses. The bridge interprets these and fans out
# device-native messages; they are NEVER forwarded as-is to a Pi.
_BRIDGE_VENTS_OFF = "/bridge/vents/off"
_BRIDGE_TROLLEY_OFF = "/bridge/trolley/off"
_BRIDGE_POSITION_PREFIX = "/bridge/position"  # exact or "/bridge/position/<id>"

# Position-mapping window: external 0..1 → trolley 0.1..0.9.
_POSITION_MIN = 0.1
_POSITION_SPAN = 0.8


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


def _parse_targeted(address: str) -> "tuple[str, str] | None":
    """Parse `/to/<identifier>/<rest>`. Returns (identifier, "/rest") or None
    if the address isn't targeted. `<rest>` keeps its leading slash so the
    forwarded address is a valid OSC path."""
    if not address.startswith("/to/"):
        return None
    remainder = address[len("/to/"):]
    if "/" not in remainder:
        # `/to/foo` with no trailing address — malformed.
        return None
    identifier, rest = remainder.split("/", 1)
    if not identifier:
        return None
    return identifier, "/" + rest


def _match_device(devices: list, identifier: str) -> "dict | None":
    """Find a device by id, name, ip_address, or hardware_id (in that order)."""
    for key in ("id", "name", "ip_address", "hardware_id"):
        for d in devices:
            if d.get(key) == identifier:
                return d
    return None


def _parse_bridge_position(address: str) -> "tuple[bool, str | None]":
    """Recognize `/bridge/position` (broadcast) or `/bridge/position/<id>`
    (single device). Returns (matched, identifier_or_None)."""
    if address == _BRIDGE_POSITION_PREFIX:
        return True, None
    prefix = _BRIDGE_POSITION_PREFIX + "/"
    if address.startswith(prefix):
        identifier = address[len(prefix):]
        if identifier:
            return True, identifier
    return False, None


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
        """Catch-all dispatcher handler: route + log + publish.

        Four dispatch paths, in order:
          1. Bridge macro: `/bridge/<command>` is intercepted and expanded
             into per-device sends; never forwarded as `/bridge/...`.
          2. Targeted: address starts with /to/<identifier>/<rest>. Look up
             a single device by id/name/ip/hardware_id and forward <rest>
             only to that device. Always wins over the routing mode.
          3. routing == "none": log but don't forward.
          4. Normal routing: type-match or passthrough over all devices.
        """
        src_ip = client_address[0] if client_address else ""
        targets: list[str] = []
        dropped: Optional[str] = None
        forwarded_address = address  # what we actually send to the Pi (stripped /to/<id>/ if present)
        expanded: Optional[list] = None  # only set for bridge macros

        devices = list(self._device_provider())

        if address.startswith("/bridge/"):
            macro = self._dispatch_bridge_macro(address, args, devices)
            targets = macro["targets"]
            dropped = macro.get("dropped")
            expanded = macro.get("expanded")
            self._record_event(
                src_ip, address, args, targets,
                forwarded_address=address,
                dropped=dropped,
                expanded=expanded,
            )
            return

        targeted = _parse_targeted(address)

        if targeted is not None:
            identifier, rest = targeted
            device = _match_device(devices, identifier)
            if device is None:
                dropped = f"no device matching {identifier!r}"
            elif not device.get("ip_address"):
                dropped = f"device {identifier!r} has no IP address"
            else:
                forwarded_address = rest
                try:
                    self._osc.send(
                        device["ip_address"],
                        device.get("osc_port", 9000),
                        rest,
                        _to_osc_value(args),
                    )
                    targets.append(device.get("id") or device["ip_address"])
                except Exception as e:
                    logger.warning("Bridge targeted forward to %s failed: %s", identifier, e)
                    dropped = f"send to {identifier!r} failed: {e}"
        elif self._routing == "none":
            dropped = "routing=none"
        else:
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

        self._record_event(
            src_ip, address, args, targets,
            forwarded_address=forwarded_address,
            dropped=dropped,
        )

    def _record_event(
        self,
        src_ip: str,
        address: str,
        args: tuple,
        targets: list,
        *,
        forwarded_address: Optional[str] = None,
        dropped: Optional[str] = None,
        expanded: Optional[list] = None,
    ) -> None:
        event = {
            "t": time.time(),
            "src": src_ip,
            "address": address,
            "args": list(args),
            "targets": targets,
        }
        # Surface the resolved address when a /to/ prefix was stripped, so the
        # UI can show "/to/X/vents/fan/1 → /vents/fan/1".
        if forwarded_address is not None and forwarded_address != address:
            event["forwarded_as"] = forwarded_address
        if dropped:
            event["dropped"] = dropped
        if expanded:
            event["expanded"] = expanded

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

    def _dispatch_bridge_macro(self, address: str, args: tuple, devices: list) -> dict:
        """Expand a `/bridge/...` macro into per-device sends.

        Returns a dict {targets, expanded?, dropped?}. Always returns a dict
        (caller already gated on the `/bridge/` prefix); unrecognized
        sub-addresses produce dropped="unknown bridge command".
        """
        if address == _BRIDGE_VENTS_OFF:
            return self._bridge_vents_off(devices)
        if address == _BRIDGE_TROLLEY_OFF:
            return self._bridge_trolley_off(devices)
        is_position, identifier = _parse_bridge_position(address)
        if is_position:
            return self._bridge_position(args, devices, identifier)
        return {"targets": [], "dropped": "unknown bridge command"}

    def _send_to(self, device: dict, address: str, value: Any) -> bool:
        """Send one OSC message to one device. Returns True on success."""
        try:
            self._osc.send(
                device["ip_address"],
                device.get("osc_port", 9000),
                address,
                value,
            )
            return True
        except Exception as e:
            logger.warning("Bridge macro send to %s failed: %s",
                           device.get("ip_address"), e)
            return False

    def _bridge_vents_off(self, devices: list) -> dict:
        """Disable auto, peltiers off, both fans to 0.0 — every vents device.

        Auto-mode is disabled FIRST so the controller's auto loop can't race
        the peltier-off command and re-enable peltiers between messages.
        """
        sequence = [
            ("/vents/mode", "raw"),
            ("/vents/peltier", 0),
            ("/vents/fan/1", 0.0),
            ("/vents/fan/2", 0.0),
        ]
        return self._fanout_to_type(devices, "vents", sequence,
                                    empty_msg="no vents devices")

    def _bridge_trolley_off(self, devices: list) -> dict:
        """`/trolley/stop` to every trolley device. python-osc rejects empty
        payloads, so we send the same `0` sentinel as the existing bang path."""
        sequence = [("/trolley/stop", _to_osc_value(()))]
        return self._fanout_to_type(devices, "trolley", sequence,
                                    empty_msg="no trolley devices")

    def _fanout_to_type(
        self,
        devices: list,
        device_type: str,
        sequence: list,
        *,
        empty_msg: str,
    ) -> dict:
        eligible = [d for d in devices
                    if d.get("type") == device_type and d.get("ip_address")]
        if not eligible:
            return {"targets": [], "dropped": empty_msg}
        targets: list[str] = []
        expanded: list[dict] = []
        for d in eligible:
            target_id = d.get("id") or d.get("ip_address")
            sent_any = False
            for addr, value in sequence:
                if self._send_to(d, addr, value):
                    expanded.append({"address": addr, "value": value, "target": target_id})
                    sent_any = True
            if sent_any:
                targets.append(target_id)
        return {"targets": targets, "expanded": expanded}

    def _bridge_position(self, args: tuple, devices: list,
                         identifier: Optional[str]) -> dict:
        """Map external 0..1 → trolley 0.1..0.9, then send /trolley/position."""
        if not args:
            return {"targets": [], "dropped": "missing or invalid position"}
        try:
            raw = float(args[0])
        except (TypeError, ValueError):
            return {"targets": [], "dropped": "missing or invalid position"}
        clamped = max(0.0, min(1.0, raw))
        mapped = _POSITION_MIN + clamped * _POSITION_SPAN

        if identifier is None:
            eligible = [d for d in devices
                        if d.get("type") == "trolley" and d.get("ip_address")]
            if not eligible:
                return {"targets": [], "dropped": "no trolley devices"}
        else:
            device = _match_device(devices, identifier)
            if device is None:
                return {"targets": [], "dropped": f"no device matching {identifier!r}"}
            if device.get("type") != "trolley":
                return {"targets": [], "dropped": "target is not a trolley"}
            if not device.get("ip_address"):
                return {"targets": [], "dropped": f"device {identifier!r} has no IP address"}
            eligible = [device]

        targets: list[str] = []
        expanded: list[dict] = []
        for d in eligible:
            target_id = d.get("id") or d.get("ip_address")
            if self._send_to(d, "/trolley/position", mapped):
                targets.append(target_id)
                expanded.append({"address": "/trolley/position",
                                 "value": mapped, "target": target_id})
        return {"targets": targets, "expanded": expanded}


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
