"""Backend configuration."""

import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DEFAULT_OSC_PORT = 9000
# Port the Pi exposes its HTTP status/test/snapshot server on
# (rpi-controller/config.py HTTP_PORT). Used by api/vents_control.py
# to fetch the discovered-probes list (which can't ride OSC).
DEFAULT_PI_HTTP_PORT = 9001
PLAYBACK_TICK_RATE = 30  # Hz


def get_data_dir(override=None):
    """Return override if given, else the default DATA_DIR."""
    return override if override is not None else DATA_DIR
