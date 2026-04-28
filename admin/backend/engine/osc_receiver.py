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
        self.trolley_status = {}  # ip_address -> {"position", "limit", "homed", "timestamp"}
        self.vents_status = {}   # ip_address -> full vents snapshot + "timestamp"
        self.server = None
        self.thread = None
        self.running = False
        self.error = None

        self.dispatcher = Dispatcher()
        self.dispatcher.map("/sys/pong", self._handle_pong, needs_reply_address=True)
        self.dispatcher.map("/trolley/status", self._handle_trolley_status, needs_reply_address=True)
        self.dispatcher.map("/vents/status", self._handle_vents_status, needs_reply_address=True)

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

    def _handle_trolley_status(self, client_address, addr, *args):
        """Pi-pushed status for trolley controllers.
        Args: (position_0_1, limit_int, homed_int [, state_str, calibrated_int]).
        Old firmware sends only the first three; treat the extras as optional.
        """
        ip = client_address[0]
        self.last_seen[ip] = time.time()
        try:
            position = float(args[0]) if len(args) > 0 else 0.0
            limit = int(args[1]) if len(args) > 1 else 0
            homed = int(args[2]) if len(args) > 2 else 0
            state = str(args[3]) if len(args) > 3 else "idle"
            calibrated = int(args[4]) if len(args) > 4 else 0
        except (TypeError, ValueError):
            return
        self.trolley_status[ip] = {
            "position": position,
            "limit": limit,
            "homed": homed,
            "state": state,
            "calibrated": calibrated,
            "timestamp": time.time(),
        }

    def _handle_vents_status(self, client_address, addr, *args):
        """Pi-pushed status for vents controllers. Arg layout matches
        controllers.vents.get_status_osc_args():
          (temp1, temp2, fan1, fan2, peltier_mask,
           rpm1A, rpm1B, rpm2A, rpm2B, target_c, mode, state [, max_temp_c])
        Missing temperatures arrive encoded as -1.0 and are exposed as None.
        Older firmware sends 12 payload args (no max_temp_c).
        """
        ip = client_address[0]
        self.last_seen[ip] = time.time()
        try:
            temp1 = float(args[0])
            temp2 = float(args[1])
            fan1 = float(args[2])
            fan2 = float(args[3])
            peltier_mask = int(args[4])
            rpm1A = int(args[5])
            rpm1B = int(args[6])
            rpm2A = int(args[7])
            rpm2B = int(args[8])
            target_c = float(args[9])
            mode = str(args[10])
            state = str(args[11])
            max_tc = float(args[12]) if len(args) > 12 else None
        except (IndexError, TypeError, ValueError):
            return
        row = {
            "temp1_c": temp1 if temp1 >= 0 else None,
            "temp2_c": temp2 if temp2 >= 0 else None,
            "fan1": fan1,
            "fan2": fan2,
            "peltier_mask": peltier_mask,
            "peltier": [bool(peltier_mask & 1), bool(peltier_mask & 2), bool(peltier_mask & 4)],
            "rpm1A": rpm1A,
            "rpm1B": rpm1B,
            "rpm2A": rpm2A,
            "rpm2B": rpm2B,
            "target_c": target_c,
            "mode": mode,
            "state": state,
            "timestamp": time.time(),
        }
        if max_tc is not None:
            row["max_temp_c"] = max_tc
        self.vents_status[ip] = row

    def get_status(self, ip: str, timeout: float = 6.0) -> bool:
        """Return True if we've seen a pong from this IP within the timeout."""
        last_time = self.last_seen.get(ip, 0)
        return (time.time() - last_time) < timeout

    def get_device_info(self, ip: str) -> dict:
        """Return {"type", "hardware_id"} last reported by the device at ip, or {} if unseen."""
        return dict(self.device_info.get(ip, {}))

    def get_trolley_status(self, ip: str) -> dict:
        """Return last {position, limit, homed, timestamp} for a trolley device, or {}."""
        return dict(self.trolley_status.get(ip, {}))

    def get_vents_status(self, ip: str) -> dict:
        """Return last vents snapshot for a vents device, or {}."""
        return dict(self.vents_status.get(ip, {}))

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
