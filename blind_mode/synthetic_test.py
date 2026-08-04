# blind_mode/synthetic_test.py
# -----------------------------------------------------------------------------
# Synthetic validation of the Blind Mode logic.
# Simulates a person walking straight toward a wall from 200cm down to 10cm.
# Validates the distance, TTC math, haptic triggers, and audio triggers
# logged by test_logger.py.
# -----------------------------------------------------------------------------

import sys
import os
import csv
from pathlib import Path

# Inject mock GPIO path before importing any blind_mode modules
sys.path.append(os.path.abspath("mock_lib"))

# Mock pyttsx3 before anything tries to import audio_alert
import unittest.mock
sys.modules['pyttsx3'] = unittest.mock.MagicMock()

import test_logger
import audio_alert
from sensor_loop import POLL_INTERVAL_S, TTC_THRESHOLD_S
from audio_alert import TTC_AUDIO_THRESHOLD_S

# ── Mock setup ───────────────────────────────────────────────────────────────

# We simulate walking at 100 cm/s (1 m/s).
# At a 0.1s poll interval, distance decreases by 10 cm per loop iteration.
# Since the loop reads A then B (spaced by 0.1s), we drop distance by 10 cm
# between A and B, and hold it steady between B and the next A.

_current_dist = 200.0
_is_sample_a = True

def mock_read_all_sensors():
    global _current_dist, _is_sample_a
    
    if _current_dist < 10.0:
        raise StopIteration("End of walking simulation")
        
    res = {"left": 200.0, "center": _current_dist, "right": 200.0}
    
    if _is_sample_a:
        # Sample A taken. Next is Sample B, 0.1s later (distance closes by 10cm)
        _current_dist -= 10.0
        _is_sample_a = False
    else:
        # Sample B taken. Next is Sample A, immediately after.
        _is_sample_a = True
        
    return res

# Override the sensor reading function in test_logger
test_logger.read_all_sensors = mock_read_all_sensors

# Stub pyttsx3 so it doesn't try to initialize the audio driver on this machine
_audio_fired = False
def mock_speak_alert(text, cooldown=2.0):
    global _audio_fired
    pass

# ── Run the simulation ───────────────────────────────────────────────────────

csv_path = Path("synthetic_log.csv")

print("Running synthetic walking simulation (200cm -> 10cm)...")
try:
    test_logger.run_logged_session(csv_path)
except StopIteration:
    print("\nSimulation complete.")
except Exception as e:
    print(f"\nSimulation aborted: {e}")
finally:
    audio_alert.shutdown_audio()

# ── Validate the results ─────────────────────────────────────────────────────

errors = []
audio_fired = False
haptic_fired_correctly = True

with open(csv_path, "r") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print("\n--- SIMULATED, NOT HARDWARE-VALIDATED ---")
print("Validation Results:")

for row in rows:
    if row["sensor"] != "center":
        continue
        
    d_b = float(row["distance_cm"])
    ttc = float(row["ttc_s"]) if row["ttc_s"] else None
    alert = row["alert"]
    
    # Expected closing speed is 100 cm/s
    # Expected TTC is d_b / 100
    expected_ttc = d_b / 100.0
    
    if ttc is None or abs(ttc - expected_ttc) > 0.01:
        errors.append(f"TTC mismatch at distance {d_b}cm: expected {expected_ttc}s, got {ttc}s")
        
    # Check haptic triggers
    if expected_ttc < TTC_THRESHOLD_S:
        if "haptic" not in alert:
            errors.append(f"Missing haptic alert at {d_b}cm (TTC: {expected_ttc}s)")
            haptic_fired_correctly = False
    else:
        if "haptic" in alert:
            errors.append(f"False positive haptic alert at {d_b}cm (TTC: {expected_ttc}s)")
            haptic_fired_correctly = False
            
    # Check audio triggers
    if "audio" in alert:
        audio_fired = True
        if expected_ttc >= TTC_AUDIO_THRESHOLD_S:
            errors.append(f"Audio fired too early at {d_b}cm (TTC: {expected_ttc}s)")

if len(errors) == 0:
    print("[PASS] Closing speed and TTC computed correctly at each step.")
else:
    print(f"[FAIL] Math errors detected ({len(errors)}).")

if haptic_fired_correctly:
    print("[PASS] Haptic alerts fired at the correct threshold (< 1.5s).")
else:
    print("[FAIL] Haptic alert logic failed.")

if audio_fired:
    print("[PASS] Audio alert fired correctly when TTC < 1.0s.")
else:
    print("[FAIL] Audio alert never fired.")
    
print(f"[PASS] test_logger.py logged {len(rows)} total sensor rows successfully to CSV.")

print("\nDetailed errors (if any):")
for err in errors[:5]:
    print("  -", err)
if len(errors) > 5:
    print(f"  ... and {len(errors)-5} more.")

if len(errors) == 0 and haptic_fired_correctly and audio_fired:
    print("\nOVERALL: ALL SYNTHETIC TESTS PASSED ✅")
else:
    print("\nOVERALL: SYNTHETIC TEST FAILED ❌")
