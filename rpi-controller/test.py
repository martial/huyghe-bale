#!/usr/bin/env python3
"""Send test OSC messages to the GPIO controller then zero all outputs."""

import sys
import time
from pythonosc.udp_client import SimpleUDPClient

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = 9000
client = SimpleUDPClient(host, port)

print(f"Sending OSC to {host}:{port}")

# Ramp A up
for v in [0.0, 0.25, 0.5, 0.75, 1.0]:
    print(f"  /gpio/a = {v}")
    client.send_message("/gpio/a", v)
    time.sleep(0.5)

# Ramp B up
for v in [0.0, 0.25, 0.5, 0.75, 1.0]:
    print(f"  /gpio/b = {v}")
    client.send_message("/gpio/b", v)
    time.sleep(0.5)

# All off
print("Zeroing all outputs")
client.send_message("/gpio/a", 0.0)
client.send_message("/gpio/b", 0.0)
print("Done")
