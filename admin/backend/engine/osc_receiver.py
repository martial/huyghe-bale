import socket
import socketserver
import threading
import time
import logging
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

logger = logging.getLogger(__name__)

class OscReceiver:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, port=9001):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(OscReceiver, cls).__new__(cls)
                cls._instance._init(port)
            return cls._instance

    def _init(self, port):
        self.port = port
        self.last_seen = {}  # ip_address -> timestamp
        self.device_info = {}  # ip_address -> {"type": str, "hardware_id": str}
        self.server = None
        self.thread = None
        self.running = False
        self.error = None

        self.dispatcher = Dispatcher()
        self.dispatcher.map("/sys/pong", self._handle_pong, needs_reply_address=True)

    def _handle_pong(self, client_address, addr, *args):
        # client_address = (ip, port) of the UDP sender (the RPi)
        # Pong args: [origin_ip, device_type, hardware_id]
        # Legacy Pis send only [origin_ip]. Parse defensively.
        ip = client_address[0]
        self.last_seen[ip] = time.time()

        device_type = "vents"  # back-compat default
        hardware_id = ""
        if len(args) >= 2 and isinstance(args[1], str) and args[1].strip():
            device_type = args[1].strip().lower()
        if len(args) >= 3 and isinstance(args[2], str):
            hardware_id = args[2].strip()

        prev = self.device_info.get(ip)
        info = {"type": device_type, "hardware_id": hardware_id}
        if prev != info:
            logger.info("Device at %s identified as type=%s hw_id=%s", ip, device_type, hardware_id)
        self.device_info[ip] = info
        logger.debug("Received /sys/pong from %s (type=%s)", ip, device_type)

    def get_status(self, ip: str, timeout: float = 6.0) -> bool:
        """Return True if we've seen a pong from this IP within the timeout."""
        last_time = self.last_seen.get(ip, 0)
        return (time.time() - last_time) < timeout

    def get_device_info(self, ip: str) -> dict:
        """Return {"type", "hardware_id"} last reported by the device at ip, or {} if unseen."""
        return dict(self.device_info.get(ip, {}))

    def start(self):
        # Stop any existing server first (handles Flask debug reloader)
        self.stop()

        try:
            # Set SO_REUSEADDR before bind so the port is freed on restart
            socketserver.UDPServer.allow_reuse_address = True
            self.server = BlockingOSCUDPServer(("0.0.0.0", self.port), self.dispatcher)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            self.error = None
            logger.info("OSC Receiver started on port %d", self.port)
        except OSError as e:
            self.running = False
            if e.errno == 48:  # Address already in use
                self.error = f"Port {self.port} already in use"
                logger.error(
                    "Port %d already in use — is the PIERRE HUYGHE BALE app running? "
                    "Quit it or run: kill $(lsof -ti:%d)", self.port, self.port
                )
            else:
                self.error = str(e)
                logger.error("Failed to start OSC receiver on port %d: %s", self.port, e)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
            logger.info("OSC Receiver stopped")
