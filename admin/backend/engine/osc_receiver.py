import socket
import socketserver
import threading
import time
import logging
from collections import deque
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

logger = logging.getLogger(__name__)

# How long a fan must be commanded > 0 before its tach is allowed to alarm.
# Spin-up from a stop, plus DS18B20 latency between command and steady-state,
# is comfortably under 3 s on the 80 mm fans on this rig.
_RPM_ALARM_DEBOUNCE_S = 3.0
# Cap on the per-device recent_alarms ring so a misbehaving device cannot
# unbounded-grow this dict.
_RECENT_ALARMS_CAP = 50

# /vents/status optional trailing args. Firmware may send 12, 13, 14, 15 or 16
# args; each entry here is appended to the snapshot only when present.
_VENTS_OPTIONAL_STATUS_FIELDS = (
    (12, "max_temp_c"),
    (13, "min_fan_pct"),
    (14, "over_temp_fan_pct"),
    (15, "max_fan_pct"),
)


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
        # Alarm state computed from /vents/status telemetry (admin-side, not
        # pushed to Pis). Per-IP, per-channel "below since" timestamp; only
        # promoted to active_alarms after _RPM_ALARM_DEBOUNCE_S.
        self._rpm_below_since = {}        # ip -> [t_or_None] * 4
        self.active_alarms = {}            # ip -> set of channel indices (0..3) currently in alarm
        self.recent_alarms = {}            # ip -> deque of {channel,event,rpm,threshold,ts}
        # Threshold for the RPM alarm. Settings PUT calls set_min_rpm_alarm
        # to update this; default mirrors api.settings.DEFAULTS['vents_min_rpm_alarm'].
        self.min_rpm_alarm = 500
        self.server = None
        self.thread = None
        self.running = False
        self.error = None

        self.dispatcher = Dispatcher()
        self.dispatcher.map("/sys/pong", self._handle_pong, needs_reply_address=True)
        self.dispatcher.map("/trolley/status", self._handle_trolley_status, needs_reply_address=True)
        self.dispatcher.map("/vents/status", self._handle_vents_status, needs_reply_address=True)

    def set_min_rpm_alarm(self, threshold: int):
        """Update the per-channel RPM alarm threshold used by the next status tick."""
        try:
            self.min_rpm_alarm = max(0, int(threshold))
        except (TypeError, ValueError):
            pass

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
           rpm1A, rpm1B, rpm2A, rpm2B, target_c, mode, state
           [, max_temp_c [, min_fan_pct, over_temp_fan_pct]])
        Missing temperatures arrive encoded as -1.0 and are exposed as None.
        Older firmware sends 12 payload args (no max_temp_c); pre-min-fan
        firmware sends 13. Newer firmware sends 15.
        """
        ip = client_address[0]
        now = time.time()
        self.last_seen[ip] = now
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
        except (IndexError, TypeError, ValueError):
            return

        # Channels 0/1 → fan 1's two tachs; 2/3 → fan 2's two tachs.
        self._update_rpm_alarms(
            ip, now,
            rpms=(rpm1A, rpm1B, rpm2A, rpm2B),
            commanded=(fan1, fan1, fan2, fan2),
        )

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
            "timestamp": now,
        }
        # Optional config echoes appended by newer firmware. Older firmware
        # may send 12 args (no max_temp_c) up through 16 args (with max_fan_pct).
        for idx, key in _VENTS_OPTIONAL_STATUS_FIELDS:
            if len(args) > idx:
                try:
                    row[key] = float(args[idx])
                except (TypeError, ValueError):
                    pass
        self.vents_status[ip] = row

    def _update_rpm_alarms(self, ip, now, rpms, commanded):
        """Update per-channel alarm state for one device.

        Enters alarm when fan is commanded > 0 AND RPM < threshold for at
        least _RPM_ALARM_DEBOUNCE_S. Exits as soon as either condition
        breaks. Records ALARM/OK transitions in `recent_alarms`, never the
        steady state.
        """
        below = self._rpm_below_since.setdefault(ip, [None, None, None, None])
        active = self.active_alarms.setdefault(ip, set())
        recent = self.recent_alarms.setdefault(ip, deque(maxlen=_RECENT_ALARMS_CAP))
        threshold = self.min_rpm_alarm

        def emit(ch, event, rpm):
            recent.append({
                "channel": ch, "event": event, "rpm": rpm,
                "threshold": threshold, "ts": now,
            })

        for ch in range(4):
            rpm = rpms[ch]
            disabled = threshold <= 0 or commanded[ch] <= 0

            if disabled or rpm >= threshold:
                below[ch] = None
                if ch in active:
                    active.discard(ch)
                    emit(ch, "ok", rpm)
                continue

            if below[ch] is None:
                below[ch] = now
            if ch not in active and (now - below[ch]) >= _RPM_ALARM_DEBOUNCE_S:
                active.add(ch)
                emit(ch, "alarm", rpm)

    def get_active_alarms(self, ip: str) -> list:
        """Return list of currently-active alarm channels (0..3) for this IP."""
        return sorted(self.active_alarms.get(ip, set()))

    def get_recent_alarms(self, ip: str) -> list:
        """Return list of recent alarm transition records for this IP."""
        return list(self.recent_alarms.get(ip, ()))

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
