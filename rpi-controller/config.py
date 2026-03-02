"""Configuration constants for the GPIO OSC controller."""

# OSC settings
OSC_PORT = 9000
OSC_ADDRESS_A = "/gpio/a"
OSC_ADDRESS_B = "/gpio/b"

# PWM settings
PWM_FREQUENCY = 1000  # Hz

# BCM pin assignments (L298N)
PIN_ENA = 12   # PWM0 → L298N Enable A
PIN_ENB = 13   # PWM1 → L298N Enable B
PIN_IN1 = 5    # Direction: HIGH for forward
PIN_IN2 = 6    # Direction: LOW for forward
PIN_IN3 = 16   # Direction: HIGH for forward
PIN_IN4 = 20   # Direction: LOW for forward
