# blind_mode/gpio_setup.py
# -----------------------------------------------------------------------------
# GPIO initialisation and teardown for TriSense — Blind Mode.
# Call setup() once at program start, cleanup() at program exit (or in a
# try/finally block so pins are always released cleanly).
# -----------------------------------------------------------------------------

import RPi.GPIO as GPIO
from config import SENSORS, MOTORS


def setup():
    """
    Initialise all Blind Mode GPIO pins.

    - Sets BCM pin numbering mode.
    - Configures every TRIG pin as OUTPUT (initially LOW).
    - Configures every ECHO pin as INPUT.
    - Configures every haptic motor pin as OUTPUT (initially LOW).

    Safe to call multiple times (GPIO.setwarnings(False) suppresses the
    "already set up" warning on repeated calls during development).
    """
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    for label, trig, echo in SENSORS:
        GPIO.setup(trig, GPIO.OUT)
        GPIO.output(trig, GPIO.LOW)   # ensure trigger starts LOW
        GPIO.setup(echo, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        print(f"  [setup] {label:6s} sensor — TRIG GPIO{trig} → OUT, ECHO GPIO{echo} → IN")

    for label, pin in MOTORS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)    # ensure motor starts OFF
        print(f"  [setup] {label:6s} motor  — GPIO{pin} → OUT (OFF)")

    print("[setup] GPIO initialisation complete.")


def cleanup():
    """
    Release all GPIO resources.
    Call this in a finally block or at program exit to leave all pins LOW
    and avoid ResourceWarning messages on the next run.
    """
    GPIO.cleanup()
    print("[cleanup] GPIO pins released.")


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running GPIO setup test...")
    try:
        setup()
        print("\nAll pins initialised successfully.")
        print("Check that no errors or warnings appeared above.")
    except Exception as e:
        print(f"[ERROR] GPIO setup failed: {e}")
    finally:
        cleanup()
        print("Test complete.")
