"""Per-controller personality modules.

Each submodule (vents, trolley) exposes the same interface:

    NAME: str                    # "vents" | "trolley"
    setup(webhooks) -> None
    cleanup() -> None
    register_osc(dispatcher) -> None
    handle_http_test(body: dict) -> dict
    get_last_osc_time() -> float
    describe() -> dict           # for logging/status
"""

from importlib import import_module


def load(device_type: str):
    """Import and return the controller module for the given type."""
    if device_type not in ("vents", "trolley"):
        raise ValueError(f"Unknown controller type: {device_type!r}")
    return import_module(f"controllers.{device_type}")
