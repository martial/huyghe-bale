"""Configuration constants for the GPIO OSC controller."""

# OSC settings
OSC_PORT = 9000
HTTP_PORT = 9001

# --- Vents (Peltier + fans + DS18B20 temp sensors) --------------------------

# BCM pin assignments
PIN_PELTIER_1 = 26
PIN_PELTIER_2 = 25
PIN_PELTIER_3 = 24
PIN_PWM_FAN_1 = 20     # cold-side fan
PIN_PWM_FAN_2 = 18     # hot-side fan
PIN_TACHO_FAN_1A = 27
PIN_TACHO_FAN_1B = 17
PIN_TACHO_FAN_2A = 23
PIN_TACHO_FAN_2B = 22

# Fan PWM behaviour
VENTS_FAN_PWM_FREQ = 1000     # Hz
VENTS_FAN_PWM_MIN_PCT = 20.0  # duty floor to keep fans spinning
VENTS_FAN_PWM_MAX_PCT = 100.0 # duty ceiling

# Bang-bang temperature control
VENTS_DEFAULT_TARGET_C = 25.0
VENTS_HYSTERESIS_C = 0.5       # +/- around target defines the deadband
VENTS_AUTO_FAN_LOW_PCT = 20.0  # fan duty while holding / coasting
VENTS_AUTO_FAN_HIGH_PCT = 80.0 # fan duty while actively cooling
VENTS_AUTO_LOOP_HZ = 4          # auto loop tick rate

# Broadcast
VENTS_STATUS_HZ = 5            # /vents/status broadcast rate (5 Hz)
VENTS_TEMP_POLL_HZ = 1         # DS18B20 read cadence (1 Hz — reads are slow)
VENTS_TACHO_MIN_DT_S = 0.005   # debounce gap for tacho edge → RPM

# --- Trolley (stepper + limit switch) ---------------------------------------

PIN_STEP_DIR = 25
PIN_STEP_PUL = 24
PIN_STEP_ENA = 23        # active LOW: GPIO.LOW enables the driver
PIN_LIM_SWITCH = 21      # input, PUD_DOWN, HIGH when limit reached

STEP_DEBOUNCE_MS = 200
TROLLEY_MAX_STEPS = 20000            # total travel between home and far end — calibrate on rig
TROLLEY_MIN_PULSE_DELAY_S = 0.0005   # fastest half-period (≈ 1 kHz)
TROLLEY_MAX_PULSE_DELAY_S = 0.01     # slowest half-period used when speed → 0+
TROLLEY_DEFAULT_SPEED_HZ = 1000      # default for /trolley/position follow
TROLLEY_STATUS_HZ = 5                # unsolicited /trolley/status broadcast rate
TROLLEY_AUTO_HOME_ON_BOOT = False
