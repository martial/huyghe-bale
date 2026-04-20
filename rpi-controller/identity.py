"""Persistent controller identity: device type and hardware id.

Each Pi stores {"type": "vents"|"trolley", "id": "<type>_<8hex>"} in a local
file on first boot. Subsequent runs reuse it. The id is reported to the
admin over OSC /sys/pong so the backend can distinguish physical devices
independently of IP address changes.

Resolution order for the type on first boot:
  1. $GPIO_OSC_TYPE environment variable (set by systemd unit)
  2. --type=<value> argv flag on gpio_osc.py
  3. Fallback: "vents" (existing Pis keep working if never re-installed)
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_TYPES = ("vents", "trolley")
DEFAULT_TYPE = "vents"

_IDENTITY_PATH = Path(os.path.expanduser("~/.config/gpio-osc/device.json"))


def _resolve_type_hint() -> str:
    env_type = os.environ.get("GPIO_OSC_TYPE", "").strip().lower()
    if env_type in VALID_TYPES:
        return env_type
    for arg in sys.argv[1:]:
        if arg.startswith("--type="):
            candidate = arg.split("=", 1)[1].strip().lower()
            if candidate in VALID_TYPES:
                return candidate
    return DEFAULT_TYPE


def _generate_id(device_type: str) -> str:
    return f"{device_type}_{secrets.token_hex(4)}"


def load_or_create() -> dict:
    """Return {"type": str, "id": str}. Creates the file on first boot."""
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        device_type = data.get("type", "").strip().lower()
        device_id = data.get("id", "").strip()
        if device_type in VALID_TYPES and device_id:
            return {"type": device_type, "id": device_id}
        logger.warning("Identity file at %s is invalid, regenerating", _IDENTITY_PATH)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Failed to read identity file %s: %s — regenerating", _IDENTITY_PATH, e)

    device_type = _resolve_type_hint()
    device_id = _generate_id(device_type)
    identity = {"type": device_type, "id": device_id}

    _IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _IDENTITY_PATH.write_text(json.dumps(identity, indent=2) + "\n")
    logger.info("Generated new identity at %s: %s", _IDENTITY_PATH, identity)
    return identity
