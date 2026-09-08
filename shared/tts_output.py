# shared/tts_output.py
# -----------------------------------------------------------------------------
# Centralized text-to-speech output for TriSense.
# Owned and managed by ModeManager to prevent cross-mode thread collisions.
# -----------------------------------------------------------------------------

import threading
import queue
import time
import pyttsx3

# ── Internal state ────────────────────────────────────────────────────────────
_speech_queue = queue.Queue()
_last_spoken_time = 0.0
_lock = threading.Lock()
_shutdown_flag = threading.Event()
_worker_thread = None


def _worker():
    global _last_spoken_time
    engine = pyttsx3.init()
    engine.setProperty("rate", 160)
    engine.setProperty("volume", 1.0)

    while not _shutdown_flag.is_set():
        try:
            text = _speech_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        engine.say(text)
        engine.runAndWait()

        with _lock:
            _last_spoken_time = time.time()

        _speech_queue.task_done()


def start_tts_worker():
    """Starts the background TTS thread. Safe to call multiple times."""
    global _worker_thread
    with _lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _shutdown_flag.clear()
            _worker_thread = threading.Thread(target=_worker, daemon=True, name="central-tts-worker")
            _worker_thread.start()


def stop_tts_worker():
    """Signals the worker thread to stop and waits for it to finish."""
    global _worker_thread
    _shutdown_flag.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)
    with _lock:
        _worker_thread = None


def speak(text: str, cooldown: float = 2.0) -> bool:
    """
    Queue a speech alert if the cooldown period has elapsed since the last one.
    
    Returns True if queued, False if suppressed by cooldown.
    """
    with _lock:
        if time.time() - _last_spoken_time < cooldown:
            return False

    _speech_queue.put(text)
    return True


if __name__ == "__main__":
    print("Testing centralized TTS. You should hear 'Test 1', a pause, and 'Test 2'.")
    start_tts_worker()
    
    queued1 = speak("Test 1")
    print(f"Test 1 queued: {queued1}")
    time.sleep(0.5)
    
    # Should be suppressed by default 2.0s cooldown
    queued_suppressed = speak("This should be suppressed")
    print(f"Suppressed alert queued: {queued_suppressed}")
    
    time.sleep(2.0)
    queued2 = speak("Test 2")
    print(f"Test 2 queued: {queued2}")
    
    # Wait for the utterance to finish before shutdown
    time.sleep(3.0)
    stop_tts_worker()
    print("Done.")
