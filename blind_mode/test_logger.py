# blind_mode/test_logger.py
# -----------------------------------------------------------------------------
# Walking-test logger for TriSense — Blind Mode.
# Runs the full sensor → TTC → haptic + audio pipeline AND appends every
# reading to a timestamped CSV file so you can calculate false-positive and
# false-negative rates after the obstacle-course test.
#
# Usage:
#   python3 test_logger.py                    # logs to auto-named file
#   python3 test_logger.py --out mytest.csv   # logs to a specific file
#
# CSV columns:
#   wall_time      — human-readable local time (YYYY-MM-DD HH:MM:SS.fff)
#   elapsed_s      — seconds since the session started
#   sensor         — "left" | "center" | "right"
#   distance_cm    — measured distance, or "" if sensor timed out
#   ttc_s          — time-to-collision in seconds, or "" if N/A
#   alert          — "haptic" | "haptic+audio" | "" (none)
#
# Stop the session with Ctrl+C. The CSV is flushed after every row so no
# data is lost if the Pi crashes mid-test.
# -----------------------------------------------------------------------------

import csv
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

from gpio_setup import setup, cleanup
from distance import read_all_sensors
from collision import compute_closing_speed, time_to_collision
from haptic import get_alert_intensity, pulse_motor
from audio_alert import speak_alert, shutdown_audio, TTC_AUDIO_THRESHOLD_S
from sensor_loop import fire_motor_async, POLL_INTERVAL_S, TTC_THRESHOLD_S
from config import SENSORS


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _make_output_path():
    """Auto-generate a log filename with the current date/time."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(__file__).parent / f"test_log_{ts}.csv"


CSV_FIELDNAMES = ["wall_time", "elapsed_s", "sensor",
                  "distance_cm", "ttc_s", "alert"]


def _write_row(writer, file_handle, session_start, sensor, distance, ttc, alert_type):
    """Append one reading row and flush immediately."""
    now = datetime.now()
    writer.writerow({
        "wall_time":   now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "elapsed_s":   f"{time.time() - session_start:.3f}",
        "sensor":      sensor,
        "distance_cm": f"{distance:.1f}" if distance is not None else "",
        "ttc_s":       f"{ttc:.2f}"      if ttc      is not None else "",
        "alert":       alert_type,
    })
    file_handle.flush()


# ── Logged sensor loop ────────────────────────────────────────────────────────

def run_logged_session(out_path):
    """
    Full pipeline loop identical to sensor_loop.run_loop() but with CSV logging.
    Runs until Ctrl+C.
    """
    session_start = time.time()
    row_count = 0

    print(f"Logging to: {out_path}")
    print("Press Ctrl+C to end the session.\n")

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        fh.flush()

        while True:
            readings_a = read_all_sensors()
            time.sleep(POLL_INTERVAL_S)
            readings_b = read_all_sensors()

            for label, _trig, _echo in SENSORS:
                d_a = readings_a[label]
                d_b = readings_b[label]

                speed = compute_closing_speed(d_a, d_b, POLL_INTERVAL_S)
                ttc   = time_to_collision(d_b, speed)

                # ── Determine alert type ──────────────────────────────────────
                alert_type = ""
                duration_ms = get_alert_intensity(ttc, threshold=TTC_THRESHOLD_S)
                if duration_ms is not None:
                    fire_motor_async(label, duration_ms)
                    alert_type = "haptic"

                if label == "center" and ttc is not None and ttc < TTC_AUDIO_THRESHOLD_S:
                    if speak_alert("Obstacle ahead"):   # True = actually spoken
                        alert_type = "haptic+audio" if alert_type else "audio"

                # ── Log row ───────────────────────────────────────────────────
                _write_row(writer, fh, session_start, label, d_b, ttc, alert_type)
                row_count += 1

            # Live terminal feedback (one overwriting line)
            elapsed = time.time() - session_start
            print(f"\r  [{elapsed:6.1f}s] {row_count} rows logged", end="", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TriSense Blind Mode — walking test logger")
    parser.add_argument("--out", default=None,
                        help="CSV output path (default: auto-named in blind_mode/)")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else _make_output_path()

    setup()
    try:
        run_logged_session(out_path)
    except KeyboardInterrupt:
        print("\n\nSession ended by user.")
    finally:
        shutdown_audio()
        cleanup()
        print(f"Data saved to: {out_path}")
        print("Open the CSV in Excel / LibreOffice to analyse false-positive"
              " and false-negative rates.")


if __name__ == "__main__":
    main()
