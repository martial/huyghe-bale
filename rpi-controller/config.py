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
# Absolute ceiling (°C): above this → over_temp / interlock (persisted on Pi when changed).
VENTS_DEFAULT_MAX_TEMP_C = 80.0
VENTS_AUTO_FAN_LOW_PCT = 20.0  # PWM floor reference (raw/manual fans); unused by auto thermoregulation
VENTS_AUTO_FAN_HIGH_PCT = 80.0 # PWM ceiling reference (raw/manual fans)
VENTS_AUTO_LOOP_HZ = 4          # auto loop tick rate

# Broadcast
VENTS_STATUS_HZ = 5            # /vents/status broadcast rate (5 Hz)
VENTS_TEMP_POLL_HZ = 1         # DS18B20 read cadence (1 Hz — reads are slow)
VENTS_TACHO_MIN_DT_S = 0.005   # debounce gap for tacho edge → RPM

# --- Trolley (dual stepper gantry + dual limit switches + per-driver diags) -
#
# Two stepper motors driven in lockstep by one shared step/dir/ena bus (one
# CL86Y driver per motor, each receiving the same PUL/DIR/ENA signals).
# Each driver has its own diagnostic outputs wired separately to the Pi:
# ALARM_1 + PEND_1 come from driver/motor 1; ALARM_2 + PEND_2 from driver 2.
# Limit switches sit at the home and far ends of the rail.
#
# Pin caveats:
#   BCM 1  (ALARM_1) is I²C-0 SDA — fine as plain GPIO when no I²C HAT is attached.
#   BCM 7  (PEND_1)  is SPI0 CE1 — fine as plain GPIO when SPI is disabled in
#                    /boot/firmware/config.txt (it is on these Pis).
#
# NOTE: only PIN_LIM_SWITCH (home end) is read by controllers/trolley.py today.
# The far-end + alarm + PEND constants are present so the bench script and any
# future ISR refactor can reference the canonical pin numbers in one place.

PIN_STEP_DIR = 23                 # DIR
PIN_STEP_PUL = 18                 # PUL
PIN_STEP_ENA = 14                 # ENA — active LOW

PIN_LIM_SWITCH      = 20          # home end — used by the firmware (single switch it knows)
PIN_LIM_SWITCH_FAR  = 21          # far end — read by scripts/test_trolley.py only (for now)

PIN_ALARM_1 = 1                   # driver fault output channel 1 (input to Pi)
PIN_ALARM_2 = 16                  # driver fault output channel 2
PIN_PEND_1  = 7                   # driver "Position-End" output channel 1
PIN_PEND_2  = 12                  # driver "Position-End" output channel 2

STEP_DEBOUNCE_MS = 200
TROLLEY_MAX_STEPS = 20000            # total travel between home and far end — calibrate on rig
TROLLEY_MIN_PULSE_DELAY_S = 0.0005   # fastest half-period (≈ 1 kHz)
TROLLEY_MAX_PULSE_DELAY_S = 0.01     # slowest half-period used when speed → 0+
TROLLEY_DEFAULT_SPEED_HZ = 1000      # default for /trolley/position follow
TROLLEY_STATUS_HZ = 5                # unsolicited /trolley/status broadcast rate
TROLLEY_AUTO_HOME_ON_BOOT = False
