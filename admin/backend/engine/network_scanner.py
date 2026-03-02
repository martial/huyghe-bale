"""Network scanner for discovering hosts on the local network."""

import ipaddress
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from pythonosc.udp_client import SimpleUDPClient


def detect_local_subnet() -> str:
    """Detect the local /24 subnet by finding this machine's LAN IP."""
    system = platform.system()
    if system == "Linux":
        try:
            out = subprocess.check_output(
                ["ip", "-4", "-o", "addr", "show"],
                timeout=5,
                text=True,
            )
            for line in out.splitlines():
                parts = line.split()
                # Skip loopback
                if "lo" in parts[1]:
                    continue
                for part in parts:
                    if "/" in part:
                        try:
                            net = ipaddress.IPv4Interface(part)
                            return str(
                                ipaddress.IPv4Network(
                                    f"{net.ip}/{24}", strict=False
                                )
                            )
                        except ValueError:
                            continue
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    # macOS fallback / general fallback: connect to a public IP to find local ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return str(ipaddress.IPv4Network(f"{local_ip}/24", strict=False))
    except OSError:
        return "192.168.1.0/24"


def _get_local_ip() -> str:
    """Get local IP to exclude from scan results."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def ping_host(ip: str) -> bool:
    """Ping a host with 1s timeout. Returns True if reachable."""
    system = platform.system()
    # macOS: -W is milliseconds; Linux: -W is seconds
    timeout_flag = ["-W", "1000"] if system == "Darwin" else ["-W", "1"]
    try:
        result = subprocess.run(
            ["ping", "-c", "1"] + timeout_flag + [ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_tcp_port(ip: str, port: int = 22) -> bool:
    """Check if a TCP port is open (default: SSH port 22)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def probe_osc_port(ip: str, port: int = 9000) -> bool:
    """Send an OSC probe message. Best-effort, always returns True if no exception."""
    try:
        client = SimpleUDPClient(ip, port)
        client.send_message("/gpio/a", 0.0)
        return True
    except OSError:
        return False


def resolve_hostname(ip: str) -> str:
    """Reverse-DNS lookup. Returns hostname or empty string on failure."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def scan_subnet_stream(subnet: str | None = None, osc_port: int = 9000):
    """Scan a /24 subnet, yielding results as they're discovered.

    Yields dicts:
      {"type": "host", "ip": "...", "hostname": "...", "ssh": bool, "potential_pi": bool, "osc_port": int}
      {"type": "done"}
    """
    if not subnet:
        subnet = detect_local_subnet()

    network = ipaddress.IPv4Network(subnet, strict=False)
    local_ip = _get_local_ip()
    hosts = [str(ip) for ip in network.hosts() if str(ip) != local_ip]

    # Ping sweep in parallel — yield each alive host immediately
    alive = set()
    hostnames: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(ping_host, ip): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                alive.add(ip)
                hostname = resolve_hostname(ip)
                hostnames[ip] = hostname
                yield {
                    "type": "host",
                    "ip": ip,
                    "hostname": hostname,
                    "ssh": False,
                    "potential_pi": False,
                    "osc_port": osc_port,
                }

    # SSH check on alive hosts — yield updates for those with SSH open
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(check_tcp_port, ip, 22): ip for ip in alive}
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                # OSC probe best-effort
                probe_osc_port(ip, osc_port)
                yield {
                    "type": "host",
                    "ip": ip,
                    "hostname": hostnames.get(ip, ""),
                    "ssh": True,
                    "potential_pi": True,
                    "osc_port": osc_port,
                }

    yield {"type": "done"}
