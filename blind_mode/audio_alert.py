# blind_mode/audio_alert.py
# -----------------------------------------------------------------------------
# Non-blocking text-to-speech alerts for TriSense — Blind Mode.
# Proxies requests to the central shared TTS engine.
#
# Usage from sensor_loop.py:
#   from audio_alert import speak_alert, shutdown_audio
#   speak_alert("Obstacle ahead")   # non-blocking; respects cooldown
#   shutdown_audio()                # legacy no-op
# -----------------------------------------------------------------------------

import os
import sys
import time

# Ensure shared module is reachable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shared.tts_output import speak, start_tts_worker, stop_tts_worker

# ── Tunable constants ─────────────────────────────────────────────────────────
AUDIO_COOLDOWN_S = 2.0    # minimum seconds between successive spoken alerts
TTC_AUDIO_THRESHOLD_S = 1.0  # speak only when center TTC drops below this


def speak_alert(text, cooldown=AUDIO_COOLDOWN_S):
    """
    Queue a speech alert via the shared central TTS engine.
    """
    return speak(text, cooldown=cooldown)


def shutdown_audio():
    """
    Legacy shutdown method. Now a no-op since ModeManager owns the TTS lifecycle.
    """
    pass


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Audio alert test — you should hear alerts 1, 3, and 4 (alert 2 silenced).")

    # The central engine must be explicitly started
    start_tts_worker()
    
    # Test 1: first alert fires immediately
    queued = speak_alert("Obstacle ahead")
    print(f"  Alert 1 queued: {queued}")   # should be True
    time.sleep(0.5)

    # Test 2: within cooldown window — should be suppressed
    queued = speak_alert("Obstacle ahead")
    print(f"  Alert 2 (within cooldown) queued: {queued}")  # should be False

    # Wait out the cooldown, then fire again
    print(f"  Waiting {AUDIO_COOLDOWN_S} s for cooldown...")
    time.sleep(AUDIO_COOLDOWN_S + 0.1)

    queued = speak_alert("Warning, obstacle on the left")
    print(f"  Alert 3 queued: {queued}")   # should be True
    time.sleep(AUDIO_COOLDOWN_S + 0.1)

    queued = speak_alert("Obstacle ahead")
    print(f"  Alert 4 queued: {queued}")   # should be True

    # Give the last utterance time to finish before shutdown
    time.sleep(3.0)
    stop_tts_worker()
    print("\nDone. You should have heard alerts 1, 3, and 4 — alert 2 silenced.")
