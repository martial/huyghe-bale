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
        self.server = None
        self.thread = None
        
        self.dispatcher = Dispatcher()
        self.dispatcher.map("/sys/pong", self._handle_pong)

    def _handle_pong(self, addr, *args):
        # We need the client IP, but python-osc doesn't easily expose it in dispatcher handlers by default 
        # unless configured. We'll pass the IP explicitly in the args to be safe.
        if not args:
            return
        ip = str(args[0])
        self.last_seen[ip] = time.time()
        logger.debug(f"Received pong from {ip}")

    def get_status(self, ip: str, timeout: float = 6.0) -> bool:
        """Return True if we've seen a pong from this IP within the timeout."""
        last_time = self.last_seen.get(ip, 0)
        return (time.time() - last_time) < timeout

    def start(self):
        if self.thread and self.thread.is_alive():
            return
            
        try:
            self.server = BlockingOSCUDPServer(("0.0.0.0", self.port), self.dispatcher)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"OSC Receiver started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start OSC receiver on port {self.port}: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
            logger.info("OSC Receiver stopped")
