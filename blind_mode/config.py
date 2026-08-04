# blind_mode/config.py
# -----------------------------------------------------------------------------
# GPIO pin definitions for TriSense — Blind Mode
# All pin numbers use BCM (Broadcom) numbering, NOT physical board numbers.
# This file contains ONLY constants — no logic, no imports.
# Change these values here if you rewire sensors or motors; everything else
# in the codebase imports from this file.
# -----------------------------------------------------------------------------

# ── Ultrasonic Sensors (HC-SR04) ─────────────────────────────────────────────
# Each sensor needs one TRIGGER output pin and one ECHO input pin.
# ECHO outputs 5V — use a 1kΩ/2kΩ voltage divider to protect the 3.3V GPIO.

TRIG_LEFT   = 5     # GPIO 5  — left sensor trigger  (~30° left of center)
ECHO_LEFT   = 6     # GPIO 6  — left sensor echo

TRIG_CENTER = 13    # GPIO 13 — center sensor trigger (straight ahead)
ECHO_CENTER = 19    # GPIO 19 — center sensor echo

TRIG_RIGHT  = 26    # GPIO 26 — right sensor trigger  (~30° right of center)
ECHO_RIGHT  = 21    # GPIO 21 — right sensor echo

# ── Haptic Vibration Motors ───────────────────────────────────────────────────
# Each motor is driven via an NPN transistor (e.g. 2N2222 / BC547).
# The GPIO pin drives the transistor base; motor current flows from 5V through
# the transistor — do NOT connect motors directly to GPIO pins.

MOTOR_LEFT   = 23   # GPIO 23 — left haptic motor
MOTOR_CENTER = 24   # GPIO 24 — center haptic motor
MOTOR_RIGHT  = 25   # GPIO 25 — right haptic motor

# ── Sensor layout summary (for reference) ────────────────────────────────────
# SENSORS is an ordered list of (label, trig_pin, echo_pin) tuples.
# Used by sensor_loop.py and test_logger.py to iterate over all three sensors
# without hard-coding the same pin pairs in multiple places.

SENSORS = [
    ("left",   TRIG_LEFT,   ECHO_LEFT),
    ("center", TRIG_CENTER, ECHO_CENTER),
    ("right",  TRIG_RIGHT,  ECHO_RIGHT),
]

# ── Haptic motor layout summary ───────────────────────────────────────────────
# MOTORS maps sensor label → motor GPIO pin.
# Used by haptic.py and sensor_loop.py.

MOTORS = {
    "left":   MOTOR_LEFT,
    "center": MOTOR_CENTER,
    "right":  MOTOR_RIGHT,
}

# ── Sensor timing ─────────────────────────────────────────────────────────────
# Maximum time (seconds) to wait for the ECHO pin to go HIGH or LOW.
# HC-SR04 max range ≈ 400 cm → round-trip ≈ 0.023 s.
# 0.03 s gives a small margin; anything beyond that is a bad reading or a
# disconnected sensor — return None instead of hanging forever.
ECHO_TIMEOUT_S = 0.03
