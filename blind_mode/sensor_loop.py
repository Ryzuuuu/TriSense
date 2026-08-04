# blind_mode/sensor_loop.py
# -----------------------------------------------------------------------------
# Live polling loop for TriSense — Blind Mode.
# Reads all three ultrasonic sensors every POLL_INTERVAL_S seconds, computes
# closing speed and time-to-collision (TTC) per sensor, prints a live
# status line, fires the correct haptic motor, and speaks a center alert
# when TTC drops below TTC_AUDIO_THRESHOLD_S.
#
# Run on the Pi:
#   python3 sensor_loop.py
# Stop with Ctrl+C.
# -----------------------------------------------------------------------------

import time
import threading

from gpio_setup import setup, cleanup
from distance import read_all_sensors
from collision import compute_closing_speed, time_to_collision
from haptic import pulse_motor, get_alert_intensity
from audio_alert import speak_alert, shutdown_audio, TTC_AUDIO_THRESHOLD_S
from config import SENSORS, MOTORS

# ── Tunable constants ─────────────────────────────────────────────────────────
POLL_INTERVAL_S  = 0.1   # seconds between each pair of samples (100 ms)
TTC_THRESHOLD_S  = 1.5   # seconds — alert if TTC is below this value
ALERT_SYMBOL     = "⚠️ " # appended to a sensor's output when TTC < threshold


def fire_motor_async(label, duration_ms):
    """
    Fire a haptic motor in a background daemon thread so the sensor loop
    is not blocked while the motor buzzes.

    Parameters
    ----------
    label       : str  Sensor/motor label ("left", "center", or "right").
    duration_ms : int  Pulse duration from get_alert_intensity().
    """
    pin = MOTORS[label]
    t = threading.Thread(target=pulse_motor, args=(pin, duration_ms), daemon=True)
    t.start()


def _format_sensor(label, distance, ttc):
    """
    Format one sensor's reading into a fixed-width string for the status line.

    Examples
    --------
    " LEFT  45cm TTC:2.3s    "
    " CENTER 22cm TTC:0.9s ⚠️ "
    " RIGHT  --- TTC:---     "
    """
    dist_str = f"{distance:5.1f}cm" if distance is not None else "  ---  "
    if ttc is not None:
        ttc_str   = f"TTC:{ttc:4.1f}s"
        alert_str = ALERT_SYMBOL if ttc < TTC_THRESHOLD_S else "   "
    else:
        ttc_str   = "TTC: --- "
        alert_str = "   "
    return f"{label.upper():6s} {dist_str} {ttc_str} {alert_str}"


def run_loop():
    """
    Main polling loop.

    On every iteration:
      1. Take sample A from all three sensors.
      2. Wait POLL_INTERVAL_S.
      3. Take sample B from all three sensors.
      4. For each sensor: compute closing speed (A→B over POLL_INTERVAL_S),
         then TTC from sample B's distance and that closing speed.
      5. Print a single status line with all three sensors.

    Runs indefinitely until Ctrl+C.
    """
    print("Sensor loop running. Press Ctrl+C to stop.\n")
    print(f"Alert threshold: TTC < {TTC_THRESHOLD_S} s\n")

    # Column headers
    header = "  |  ".join(f"{s[0].upper():6s}  dist     TTC    alert" for s in SENSORS)
    print("  " + header)
    print("  " + "-" * len(header))

    while True:
        # ── Sample A ─────────────────────────────────────────────────────────
        readings_a = read_all_sensors()

        # ── Wait one poll interval ────────────────────────────────────────────
        time.sleep(POLL_INTERVAL_S)

        # ── Sample B ─────────────────────────────────────────────────────────
        readings_b = read_all_sensors()

        # ── Compute closing speed + TTC per sensor ────────────────────────────
        parts = []
        for label, _trig, _echo in SENSORS:
            d_a = readings_a[label]
            d_b = readings_b[label]

            speed = compute_closing_speed(d_a, d_b, POLL_INTERVAL_S)
            ttc   = time_to_collision(d_b, speed)

            # ── Fire haptic motor if TTC is within alert range ─────────────────
            duration_ms = get_alert_intensity(ttc, threshold=TTC_THRESHOLD_S)
            if duration_ms is not None:
                fire_motor_async(label, duration_ms)

            # ── Speak audio alert for CENTER sensor only ───────────────────────
            if label == "center" and ttc is not None and ttc < TTC_AUDIO_THRESHOLD_S:
                speak_alert("Obstacle ahead")

            parts.append(_format_sensor(label, d_b, ttc))

        # ── Print one status line (overwrite in place) ────────────────────────
        status_line = "  |  ".join(parts)
        # \r returns to start of line; end="" keeps cursor on same line
        print(f"\r  {status_line}", end="", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup()
    try:
        run_loop()
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        shutdown_audio()
        cleanup()
        print("GPIO released. Exiting.")
