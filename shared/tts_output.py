# shared/tts_output.py
# -----------------------------------------------------------------------------
# Centralized text-to-speech output for TriSense.
# Owned and managed by ModeManager to prevent cross-mode thread collisions.
#
# Fixes over v1:
#   * the cooldown is stamped when a phrase is QUEUED, per phrase. v1 stamped
#     it only after speech finished, so a 10 Hz sensor loop could queue the same
#     warning a dozen times while the first one was still being spoken.
#   * the queue is bounded and flush() drops stale phrases on a mode switch,
#     so the device never reads out old obstacle warnings in Mute Mode.
#   * COM is initialised inside the worker thread on Windows, otherwise
#     pyttsx3 (SAPI5) fails with "CoInitialize has not been called".
# -----------------------------------------------------------------------------

import os
import queue
import sys
import threading
import time

try:
    import pyttsx3
except (ImportError, OSError):  # headless box or missing speech backend
    pyttsx3 = None

MAX_PENDING = 3          # older phrases are dropped beyond this backlog
GLOBAL_GAP_S = 0.3       # minimum gap between any two queued phrases

# ── Internal state ────────────────────────────────────────────────────────────
_speech_queue: "queue.Queue[str]" = queue.Queue()
_last_queued: dict = {}
_last_any = 0.0
_lock = threading.Lock()
_shutdown_flag = threading.Event()
_worker_thread = None
spoken_log: list = []    # phrases actually delivered (handy for tests and the emulator)
_listeners: list = []    # callables(text) notified whenever a phrase is delivered
# Set TRISENSE_TTS_CONSOLE=1 to skip the speech engine (the web emulator speaks in the browser instead)
USE_ENGINE = os.getenv("TRISENSE_TTS_CONSOLE", "0") != "1"


def add_listener(fn):
    """Register fn(text) to be called each time a phrase is spoken."""
    if fn not in _listeners:
        _listeners.append(fn)


def remove_listener(fn):
    if fn in _listeners:
        _listeners.remove(fn)


def _init_engine():
    """Returns a configured pyttsx3 engine, or None if speech output is unavailable."""
    if pyttsx3 is None:
        print("[TTS] pyttsx3 not available - speech will be logged to the console only.")
        return None
    if sys.platform == "win32":
        try:
            import pythoncom  # provided by pywin32, which pyttsx3 depends on
            pythoncom.CoInitialize()
        except Exception:
            pass
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)
        return engine
    except Exception as e:  # driver missing (e.g. no espeak on Linux)
        print(f"[TTS] Could not initialise speech engine ({e}) - logging to console only.")
        return None


def _worker():
    engine = _init_engine() if USE_ENGINE else None
    while not _shutdown_flag.is_set():
        try:
            text = _speech_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        try:
            if engine is not None:
                engine.say(text)
                engine.runAndWait()
            else:
                print(f"[TTS] {text}")
            spoken_log.append(text)
            del spoken_log[:-50]
            for fn in list(_listeners):
                try:
                    fn(text)
                except Exception as e:
                    print(f"[TTS] listener failed: {e}")
        except Exception as e:
            print(f"[TTS] speech failed ({e}): {text}")
        finally:
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


def flush():
    """Drops every phrase that has not been spoken yet (used on mode switches)."""
    while True:
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except queue.Empty:
            break


def is_running() -> bool:
    return _worker_thread is not None and _worker_thread.is_alive()


def speak(text: str, cooldown: float = 2.0) -> bool:
    """
    Queue a phrase unless the same phrase was queued less than `cooldown`
    seconds ago. Returns True if queued, False if suppressed.
    """
    global _last_any
    now = time.monotonic()
    with _lock:
        if now - _last_queued.get(text, -1e9) < cooldown or now - _last_any < GLOBAL_GAP_S:
            return False
        _last_queued[text] = now
        _last_any = now
        while _speech_queue.qsize() >= MAX_PENDING:
            try:
                _speech_queue.get_nowait()
                _speech_queue.task_done()
            except queue.Empty:
                break
        _speech_queue.put(text)
    return True


def reset_cooldowns():
    global _last_any
    with _lock:
        _last_queued.clear()
        _last_any = 0.0


if __name__ == "__main__":
    print("Testing centralized TTS. You should hear 'Test 1', a pause, and 'Test 2'.")
    start_tts_worker()

    queued1 = speak("Test 1")
    print(f"Test 1 queued: {queued1}")
    time.sleep(0.5)

    # Same phrase within the 2 s cooldown -> suppressed
    queued_suppressed = speak("Test 1")
    print(f"Repeated phrase queued: {queued_suppressed}")

    time.sleep(2.0)
    queued2 = speak("Test 2")
    print(f"Test 2 queued: {queued2}")

    time.sleep(3.0)
    stop_tts_worker()
    print("Done.")
