# blind_mode/audio_alert.py
# -----------------------------------------------------------------------------
# Non-blocking text-to-speech alerts for TriSense — Blind Mode.
# Uses pyttsx3 (fully offline, no network required) running in a dedicated
# background worker thread fed by a Queue, so the sensor loop is never blocked.
#
# Usage from sensor_loop.py:
#   from audio_alert import speak_alert, shutdown_audio
#   speak_alert("Obstacle ahead")   # non-blocking; respects cooldown
#   shutdown_audio()                # call at exit to stop the worker thread
#
# Standalone test (no GPIO needed, runs on laptop):
#   python3 audio_alert.py
# -----------------------------------------------------------------------------

import threading
import queue
import time
import pyttsx3

# ── Tunable constants ─────────────────────────────────────────────────────────
AUDIO_COOLDOWN_S = 2.0    # minimum seconds between successive spoken alerts
TTC_AUDIO_THRESHOLD_S = 1.0  # speak only when center TTC drops below this

# ── Internal state ────────────────────────────────────────────────────────────
_speech_queue     = queue.Queue()
_last_spoken_time = 0.0        # epoch seconds of the last completed speech
_lock             = threading.Lock()
_shutdown_flag    = threading.Event()


def _worker():
    """
    Background thread: keeps a single pyttsx3 engine alive and speaks
    whatever text arrives on _speech_queue.
    Initialising the engine once here (not per call) avoids repeated startup
    overhead and the driver-reinitialisation errors some platforms throw.
    """
    global _last_spoken_time
    engine = pyttsx3.init()
    engine.setProperty("rate", 160)    # slightly slower than default for clarity
    engine.setProperty("volume", 1.0)  # max volume

    while not _shutdown_flag.is_set():
        try:
            text = _speech_queue.get(timeout=0.2)   # unblocks every 200 ms to check shutdown
        except queue.Empty:
            continue

        engine.say(text)
        engine.runAndWait()             # blocks until this utterance finishes

        with _lock:
            _last_spoken_time = time.time()

        _speech_queue.task_done()


# Start the worker thread as a daemon so it exits automatically if the main
# program crashes without calling shutdown_audio().
_worker_thread = threading.Thread(target=_worker, daemon=True, name="tts-worker")
_worker_thread.start()


def speak_alert(text, cooldown=AUDIO_COOLDOWN_S):
    """
    Queue a speech alert if the cooldown period has elapsed since the last one.

    Parameters
    ----------
    text     : str    Text for pyttsx3 to speak.
    cooldown : float  Minimum gap in seconds between alerts (default 2.0 s).

    Returns
    -------
    bool  True if the alert was queued, False if suppressed by cooldown.
    """
    with _lock:
        if time.time() - _last_spoken_time < cooldown:
            return False   # still within cooldown window — skip

    _speech_queue.put(text)
    return True


def shutdown_audio():
    """
    Signal the worker thread to stop and wait for it to finish.
    Call this in a finally block at program exit.
    """
    _shutdown_flag.set()
    _worker_thread.join(timeout=2.0)


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Audio alert test — you should hear three spoken alerts with pauses.\n")

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
    shutdown_audio()
    print("\nDone. You should have heard alerts 1, 3, and 4 — alert 2 silenced.")
