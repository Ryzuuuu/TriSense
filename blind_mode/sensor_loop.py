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
from haptic import HapticDriver, pulse_motor
from audio_alert import speak_alert, shutdown_audio
from engine import BlindEngine, PROXIMITY_WARN_CM
from config import SENSORS, MOTORS, POLL_INTERVAL_S, TTC_ALERT_S

# ── Tunable constants ─────────────────────────────────────────────────────────
TTC_THRESHOLD_S  = TTC_ALERT_S  # seconds — alert if TTC is below this value
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

    Every POLL_INTERVAL_S the three sensors are read and passed, with the real
    timestamp, to BlindEngine, which filters the readings, estimates closing
    speed and time to collision, and decides on haptic pulses and speech.
    Motors are driven by the non blocking HapticDriver, so the loop never
    stalls while a motor buzzes.

    Runs indefinitely until Ctrl+C.
    """
    print("Sensor loop running. Press Ctrl+C to stop.\n")
    print(f"Alert threshold: TTC < {TTC_THRESHOLD_S} s, proximity < {PROXIMITY_WARN_CM:.0f} cm\n")

    engine = BlindEngine([s[0] for s in SENSORS])
    driver = HapticDriver()
    try:
        next_t = time.monotonic()
        while True:
            readings = read_all_sensors()
            states = engine.step(readings, time.monotonic())
            for st in states:
                if st.pulse_ms:
                    driver.pulse(st.label, st.pulse_ms)
            phrase = BlindEngine.speech_for(states)
            if phrase:
                speak_alert(phrase)
            status_line = "  |  ".join(_format_sensor(st.label, st.distance, st.ttc) for st in states)
            print(f"\r  {status_line}", end="", flush=True)
            next_t += POLL_INTERVAL_S
            time.sleep(max(0.0, next_t - time.monotonic()))
    finally:
        driver.stop()


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
