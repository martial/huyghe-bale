"""Shared fixtures and mocks for rpi-controller tests.

Mocks RPi.GPIO and pythonosc at the sys.modules level so gpio_osc
can be imported on macOS / CI without real hardware.
"""

import sys
from unittest.mock import MagicMock

import pytest


# --- Mock RPi.GPIO before anything imports it ---

_mock_gpio = MagicMock()
_mock_gpio.BCM = 11
_mock_gpio.OUT = 0
_mock_gpio.HIGH = 1
_mock_gpio.LOW = 0

_mock_pwm = MagicMock()
_mock_gpio.PWM.return_value = _mock_pwm

sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = _mock_gpio

# --- Mock pythonosc ---

sys.modules["pythonosc"] = MagicMock()
sys.modules["pythonosc.dispatcher"] = MagicMock()
sys.modules["pythonosc.osc_server"] = MagicMock()
sys.modules["pythonosc.udp_client"] = MagicMock()


@pytest.fixture
def mock_gpio():
    """Provide the mock GPIO module and reset it between tests."""
    _mock_gpio.reset_mock()
    _mock_pwm.reset_mock()
    _mock_gpio.BCM = 11
    _mock_gpio.OUT = 0
    _mock_gpio.HIGH = 1
    _mock_gpio.LOW = 0
    _mock_gpio.PWM.return_value = _mock_pwm
    return _mock_gpio


@pytest.fixture
def mock_pwm():
    """Provide the mock PWM instance."""
    _mock_pwm.reset_mock()
    return _mock_pwm
