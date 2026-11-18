# blind_mode/haptic.py
# -----------------------------------------------------------------------------
# Haptic vibration motor control for TriSense — Blind Mode.
# Each motor is wired via an NPN transistor driver — GPIO pin HIGH turns the
# motor ON, GPIO LOW turns it OFF.
#
# Run on the Pi to test all three motors in sequence:
#   python3 haptic.py
# -----------------------------------------------------------------------------

import time
import RPi.GPIO as GPIO

from gpio_setup import setup, cleanup
from config import MOTORS


def pulse_motor(pin, duration_ms):
    """
    Vibrate one haptic motor for a fixed duration then stop.

    Parameters
    ----------
    pin         : int    BCM GPIO pin number connected to the motor driver.
    duration_ms : float  How long to keep the motor ON, in milliseconds.
                         Must be > 0; values < 10 ms may not produce a
                         perceptible vibration with most motors.

    Notes
    -----
    This is a blocking call — it holds execution for duration_ms ms.
    For non-blocking use, call this from a threading.Thread (added in Step 11
    when haptics are integrated into the sensor loop).
    """
    if duration_ms <= 0:
        return
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(duration_ms / 1000.0)
    GPIO.output(pin, GPIO.LOW)


def get_alert_intensity(ttc, threshold=1.5):
    """
    Map a time-to-collision value to a haptic pulse duration.

    Parameters
    ----------
    ttc       : float | None  Time-to-collision in seconds from time_to_collision().
    threshold : float         TTC above which no alert is needed (default 1.5 s).

    Returns
    -------
    int | None
        Pulse duration in milliseconds, or None if no alert should fire.

        TTC zones (tunable):
          < 0.5 s  →  500 ms  (critical — imminent impact)
          0.5–1.0 s →  300 ms  (urgent)
          1.0–1.5 s →  150 ms  (warning)
          ≥ threshold → None    (no alert)
          None input → None    (bad sensor data)
    """
    if ttc is None:
        return None
    if ttc < 0.5:
        return 500
    if ttc < 1.0:
        return 300
    if ttc < threshold:
        return 150
    return None


class HapticDriver:
    """
    Non blocking driver for all haptic motors.

    The ModeManager adapter used to call pulse_motor() inline, which froze the
    sensor loop for up to 500 ms per motor. Here a single background thread
    switches motors off when their pulse expires, and a motor that is already
    buzzing is not re-triggered until its pulse plus a short gap has passed,
    so overlapping pulses cannot cut each other short and the wearer feels
    distinct buzzes whose length encodes urgency.
    """

    GAP_MS = 120

    def __init__(self, motors=None, gpio=None):
        import threading
        self._gpio = gpio or GPIO
        self._motors = dict(motors or MOTORS)
        self._off_at = {lb: 0.0 for lb in self._motors}
        self._next_ok = {lb: 0.0 for lb in self._motors}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="haptic-driver")
        self._thread.start()

    def pulse(self, label, duration_ms):
        """Request a pulse; returns True if it started, False if the motor is still busy."""
        if not duration_ms or label not in self._motors:
            return False
        now = time.monotonic()
        with self._lock:
            if now < self._next_ok[label]:
                return False
            self._gpio.output(self._motors[label], self._gpio.HIGH)
            self._off_at[label] = now + duration_ms / 1000.0
            self._next_ok[label] = self._off_at[label] + self.GAP_MS / 1000.0
        return True

    def _run(self):
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                for lb, t_off in self._off_at.items():
                    if t_off and now >= t_off:
                        self._gpio.output(self._motors[lb], self._gpio.LOW)
                        self._off_at[lb] = 0.0
            self._stop.wait(0.01)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=0.5)
        with self._lock:
            for lb, pin in self._motors.items():
                self._gpio.output(pin, self._gpio.LOW)
                self._off_at[lb] = 0.0


# ── Unit tests for get_alert_intensity ─────────────────────────────────────

def _test_get_alert_intensity():
    # Critical zone: TTC < 0.5 s → 500 ms pulse
    assert get_alert_intensity(0.1)  == 500, "Failed: TTC=0.1"
    assert get_alert_intensity(0.49) == 500, "Failed: TTC=0.49"

    # Urgent zone: 0.5 ≤ TTC < 1.0 s → 300 ms pulse
    assert get_alert_intensity(0.5)  == 300, "Failed: TTC=0.5"
    assert get_alert_intensity(0.99) == 300, "Failed: TTC=0.99"

    # Warning zone: 1.0 ≤ TTC < 1.5 s → 150 ms pulse
    assert get_alert_intensity(1.0)  == 150, "Failed: TTC=1.0"
    assert get_alert_intensity(1.49) == 150, "Failed: TTC=1.49"

    # At or above threshold → None (no alert)
    assert get_alert_intensity(1.5)  is None, "Failed: TTC=1.5"
    assert get_alert_intensity(5.0)  is None, "Failed: TTC=5.0"

    # None input → None
    assert get_alert_intensity(None) is None, "Failed: TTC=None"

    # Custom threshold: TTC=1.2 with threshold=1.0 → None (above custom threshold)
    assert get_alert_intensity(1.2, threshold=1.0) is None, "Failed: custom threshold"

    print("  [PASS] All get_alert_intensity tests passed.")


# ── Standalone test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1. Run unit tests first (no hardware needed for this part)
    print("Running get_alert_intensity unit tests...")
    _test_get_alert_intensity()
    print()

    # 2. Physical motor test
    print("Haptic motor test — firing each motor in sequence.")
    print("You should feel three distinct buzzes: LEFT → CENTER → RIGHT.\n")

    setup()
    try:
        for label, pin in MOTORS.items():
            print(f"  Pulsing {label.upper()} motor (GPIO {pin}) for 500 ms...")
            pulse_motor(pin, 500)
            time.sleep(0.5)

        print("\nTest complete. Did all three motors vibrate?")
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cleanup()
        print("GPIO released.")
