# blind_mode/distance.py
# -----------------------------------------------------------------------------
# Distance measurement for a single HC-SR04 ultrasonic sensor.
# The __main__ block reads the CENTER sensor only and prints a live reading
# every 500 ms for 10 seconds — enough to confirm one sensor works before
# wiring all three.
# -----------------------------------------------------------------------------

import time
import RPi.GPIO as GPIO

from gpio_setup import setup, cleanup
from config import TRIG_CENTER, ECHO_CENTER, SENSORS, ECHO_TIMEOUT_S


def get_distance(trig, echo, timeout=ECHO_TIMEOUT_S):
    """
    Trigger one ultrasonic pulse and return the measured distance in cm.

    Parameters
    ----------
    trig    : int    BCM pin number for the TRIGGER output
    echo    : int    BCM pin number for the ECHO input
    timeout : float  Max seconds to wait for echo (default ECHO_TIMEOUT_S).
                     Returns None if the echo never arrives — prevents the
                     function from hanging on a disconnected or faulty sensor.

    Returns
    -------
    float | None  Distance in cm, or None on timeout.
    """
    # Send a 10 µs HIGH pulse on the TRIG pin to start the measurement
    GPIO.output(trig, GPIO.HIGH)
    time.sleep(0.00001)          # 10 µs
    GPIO.output(trig, GPIO.LOW)

    # Wait for ECHO to go HIGH — bail out if it takes too long
    start = time.time()
    while GPIO.input(echo) == 0:
        start = time.time()
        if (start - time.time() + timeout) < 0:   # re-evaluated each iteration
            return None

    # Capture the moment ECHO went HIGH, then wait for it to go LOW
    pulse_start = time.time()
    pulse_end   = pulse_start
    while GPIO.input(echo) == 1:
        pulse_end = time.time()
        if (pulse_end - pulse_start) > timeout:
            return None           # echo stuck HIGH — sensor fault or no return

    # Distance = (round-trip time × speed of sound) / 2
    elapsed  = pulse_end - pulse_start
    distance = (elapsed * 34300) / 2
    return distance


def read_all_sensors():
    """
    Read all three sensors (left, center, right) in sequence.

    Returns
    -------
    dict  {label: distance_cm}  e.g. {"left": 45.2, "center": 82.1, "right": 30.7}
          A label's value is None if get_distance() is not yet timeout-protected
          and the sensor is disconnected — timeout safety is added in Step 5.
    """
    readings = {}
    for label, trig, echo in SENSORS:
        readings[label] = get_distance(trig, echo)
        time.sleep(0.02)  # short delay to let echoes die out and prevent cross-talk
    return readings


# ── Standalone test: all three sensors ───────────────────────────────────────
if __name__ == "__main__":
    print("Distance test — ALL THREE sensors")
    print("Wave your hand in front of each sensor in turn.")
    print("Reading every 500 ms for 15 seconds. Press Ctrl+C to stop early.\n")
    print(f"  {'LEFT':>10}   {'CENTER':>10}   {'RIGHT':>10}")
    print("  " + "-" * 38)

    setup()
    try:
        end_time = time.time() + 15
        while time.time() < end_time:
            r = read_all_sensors()
            left   = f"{r['left']:6.1f} cm"   if r['left']   is not None else "  ---   "
            center = f"{r['center']:6.1f} cm" if r['center'] is not None else "  ---   "
            right  = f"{r['right']:6.1f} cm"  if r['right']  is not None else "  ---   "
            print(f"  {left:>10}   {center:>10}   {right:>10}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cleanup()
        print("Done.")
