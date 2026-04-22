"""Configuration constants for the GPIO OSC controller."""

# OSC settings
OSC_PORT = 9000
HTTP_PORT = 9001
OSC_ADDRESS_A = "/gpio/a"
OSC_ADDRESS_B = "/gpio/b"

# PWM settings (vents)
PWM_FREQUENCY = 1000  # Hz

# BCM pin assignments (L298N — vents)
PIN_ENA = 12   # PWM0 → L298N Enable A
PIN_ENB = 13   # PWM1 → L298N Enable B
PIN_IN1 = 5    # Direction: HIGH for forward
PIN_IN2 = 6    # Direction: LOW for forward
PIN_IN3 = 16   # Direction: HIGH for forward
PIN_IN4 = 20   # Direction: LOW for forward

# BCM pin assignments (stepper — trolley)
PIN_STEP_DIR = 25
PIN_STEP_PUL = 24
PIN_STEP_ENA = 23        # active LOW: GPIO.LOW enables the driver
PIN_LIM_SWITCH = 21      # input, PUD_DOWN, HIGH when limit reached

# Stepper behaviour
STEP_DEBOUNCE_MS = 200
TROLLEY_MAX_STEPS = 20000            # total travel between home and far end — calibrate on rig
TROLLEY_MIN_PULSE_DELAY_S = 0.0005   # fastest half-period (≈ 1 kHz)
TROLLEY_MAX_PULSE_DELAY_S = 0.01     # slowest half-period used when speed → 0+
TROLLEY_DEFAULT_SPEED_HZ = 1000      # default for /trolley/position follow
TROLLEY_STATUS_HZ = 5                # unsolicited /trolley/status broadcast rate
TROLLEY_AUTO_HOME_ON_BOOT = False
