# shared/mode_manager.py
# -----------------------------------------------------------------------------
# TriSense Mode Manager (Step 1 Skeleton).
# Coordinates switching between operational pipelines (Blind Mode, Deaf Mode,
# and an extension point for Mute Mode) without modifying their internal code.
# Enforces single-owner resource locking for shared hardware subsystems
# (SPEAKER, CAMERA, MICROPHONE, DISPLAY, GPIO) so two modes never run
# simultaneously. Includes a mock keyboard trigger standing in for GPIO button.
# -----------------------------------------------------------------------------

import os
import sys
import threading
import time
from typing import Callable, Dict, Optional, Set

from shared.tts_output import flush as flush_tts, start_tts_worker, stop_tts_worker


def _ensure_headless_compat():
    """Fall back to the bundled mock RPi.GPIO when running on a PC without physical GPIO."""
    try:
        import RPi.GPIO  # noqa: F401
    except ImportError:
        mock_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "blind_mode", "mock_lib"))
        if mock_lib_path not in sys.path:
            sys.path.insert(0, mock_lib_path)


class ResourceLockError(RuntimeError):
    """Raised when attempting to acquire a hardware resource already held by another mode."""
    pass


class ResourceGuard:
    """
    Single-owner hardware resource lock manager.
    Tracks exclusive ownership of shared system resources.
    """
    def __init__(self):
        self._lock = threading.Lock()
        # Maps resource_name -> current_owner_mode ("BLIND", "DEAF", "MUTE", etc.)
        self._owners: Dict[str, str] = {}

    def acquire(self, owner: str, resources: Set[str]) -> bool:
        """
        Acquires exclusive access to all specified resources for 'owner'.
        Raises ResourceLockError if any requested resource is held by a different owner.
        """
        with self._lock:
            # First check if any requested resource is held by another mode
            for res in resources:
                current = self._owners.get(res)
                if current is not None and current != owner:
                    raise ResourceLockError(
                        f"Cannot acquire '{res}' for mode '{owner}': already held by mode '{current}'."
                    )
            # Grant ownership of all requested resources
            for res in resources:
                self._owners[res] = owner
            print(f"[RESOURCE_GUARD] Mode '{owner}' acquired resources: {sorted(list(resources))}")
            return True

    def release(self, owner: str):
        """
        Releases all resources currently held by 'owner'.
        """
        with self._lock:
            released = [res for res, curr in self._owners.items() if curr == owner]
            for res in released:
                del self._owners[res]
            if released:
                print(f"[RESOURCE_GUARD] Mode '{owner}' released resources: {sorted(released)}")

    def get_owner(self, resource: str) -> Optional[str]:
        with self._lock:
            return self._owners.get(resource)

    def get_held_resources(self, owner: str) -> Set[str]:
        with self._lock:
            return {res for res, curr in self._owners.items() if curr == owner}

    def snapshot(self) -> Dict[str, str]:
        """Returns a copy of the current resource -> owner map."""
        with self._lock:
            return dict(self._owners)

    def clear(self):
        with self._lock:
            self._owners.clear()


class BlindModePipeline:
    """
    Adapter for Blind Mode. Uses the same BlindEngine as `blind_mode/sensor_loop.py`.

    v1 called pulse_motor() inline (freezing the loop for up to 1.5 s per
    cycle) and still divided by a fixed 0.1 s, so speeds and TTCs were wrong
    whenever an alert fired. Now motors are driven by the non blocking
    HapticDriver and the engine uses real timestamps.
    """
    REQUIRED_RESOURCES = {"SPEAKER", "GPIO_SENSORS", "GPIO_MOTORS"}

    def __init__(self):
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._driver = None
        self.on_telemetry: Optional[Callable] = None
        self.on_state: Optional[Callable] = None

    def start(self, **kwargs):
        if self.is_running:
            return
        # Optional callback(label, distance_cm, ttc_s, pulse_ms) used by the web emulator
        self.on_telemetry = kwargs.get("on_telemetry")
        # Optional callback(states, phrase) with the full engine output for every cycle
        self.on_state = kwargs.get("on_state")
        print("[BLIND_PIPELINE] Starting Blind Mode ultrasonic/haptic pipeline...")
        _ensure_headless_compat()
        from blind_mode.gpio_setup import setup
        from blind_mode.haptic import HapticDriver
        setup()
        self._driver = HapticDriver()
        self._stop_evt.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop_wrapper, daemon=True, name="blind-loop")
        self._thread.start()

    def _run_loop_wrapper(self):
        _ensure_headless_compat()
        from blind_mode.distance import read_all_sensors
        from blind_mode.engine import BlindEngine
        from blind_mode.audio_alert import speak_alert
        from blind_mode.config import SENSORS, POLL_INTERVAL_S

        engine = BlindEngine([s[0] for s in SENSORS])
        next_t = time.monotonic()
        while not self._stop_evt.is_set():
            readings = read_all_sensors()
            states = engine.step(readings, time.monotonic())
            for st in states:
                if st.pulse_ms:
                    self._driver.pulse(st.label, st.pulse_ms)
                if self.on_telemetry:
                    self.on_telemetry(st.label, st.distance, st.ttc, st.pulse_ms)
            phrase = BlindEngine.speech_for(states)
            if phrase:
                speak_alert(phrase)
            if self.on_state:
                self.on_state(states, phrase)
            next_t += POLL_INTERVAL_S
            delay = next_t - time.monotonic()
            if delay < -POLL_INTERVAL_S:  # fell far behind (slow sensors): resynchronise
                next_t = time.monotonic()
            self._stop_evt.wait(max(0.0, delay))

    def stop(self):
        if not self.is_running:
            return
        print("[BLIND_PIPELINE] Stopping Blind Mode pipeline...")
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._driver:
            self._driver.stop()
            self._driver = None
        from blind_mode.gpio_setup import cleanup
        cleanup()
        self.is_running = False
        print("[BLIND_PIPELINE] Blind Mode stopped and GPIO released.")


class DeafModePipeline:
    """
    Adapter for Deaf Mode (`deaf_mode/main_loop.py`).

    v1 ran the whole recognition loop inside start(), so switch_mode() did not
    return until the audio source ended. With a live microphone that meant
    forever, and the user could never switch away from Deaf Mode. The app now
    runs in a background thread and stop() ends it.
    """
    REQUIRED_RESOURCES = {"MICROPHONE", "DISPLAY"}

    def __init__(self):
        self.is_running = False
        self.app = None
        self.summary = None
        self._thread: Optional[threading.Thread] = None

    def start(self, wav_path=None, use_mock=True, wait=False, **kwargs):
        if self.is_running:
            return
        print("[DEAF_PIPELINE] Starting Deaf Mode speech-to-text pipeline...")
        from deaf_mode.audio_stream import AudioStreamer
        from deaf_mode.asr_engine import ASREngine
        from deaf_mode.caption_formatter import CaptionFormatter
        from deaf_mode.oled_display import OLEDDisplay
        from deaf_mode.caption_renderer import CaptionRenderer
        from deaf_mode.main_loop import DeafModeApp

        audio_source = kwargs.get("audio_source")  # e.g. PushAudioStreamer fed by the browser microphone
        if audio_source is not None:
            audio_streamer = audio_source
            asr_engine = ASREngine(sample_rate=16000)
        else:
            audio_streamer = AudioStreamer(callback=None, sample_rate=16000, block_size=4000,
                                           wav_path=wav_path, use_mock=use_mock)
            # Real Vosk whenever the model is installed; the mock recogniser only for synthetic audio
            asr_engine = ASREngine(sample_rate=16000, use_mock=True if (use_mock and not wav_path) else None)
        formatter = CaptionFormatter(max_chars_per_line=20, max_lines=3)
        display = OLEDDisplay(width=128, height=64, use_mock=kwargs.get("mock_display", use_mock))
        renderer = CaptionRenderer(display=display, formatter=formatter, default_header="TriSense ASR [REC]")

        self.app = DeafModeApp(
            audio_streamer=audio_streamer,
            asr_engine=asr_engine,
            renderer=renderer,
            on_caption_update=kwargs.get("on_caption_update")
        )
        self.is_running = True
        real_time = kwargs.get("real_time", bool(wav_path) and not wait)
        self._thread = threading.Thread(target=self._run, args=(real_time,), daemon=True, name="deaf-app")
        self._thread.start()
        if wait:  # tests / batch transcription: block until the source is exhausted
            self._thread.join()

    def _run(self, real_time):
        try:
            self.summary = self.app.run(real_time=real_time)
        except Exception as e:
            print(f"[DEAF_PIPELINE] Deaf Mode crashed: {e}")
            self.summary = {"error": str(e)}

    def stop(self):
        if not self.is_running:
            return
        print("[DEAF_PIPELINE] Stopping Deaf Mode pipeline...")
        if self.app:
            self.app.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.is_running = False
        print("[DEAF_PIPELINE] Deaf Mode stopped.")


class MuteModePipeline:
    """
    Mute Mode (Sign Language Recognition -> Speech). Uses camera input and speaker output.

    Uses the v2 recogniser (hands + upper body landmarks, activity based sign
    segmentation, SignClassifierV2) when checkpoints/sign_v2.pth exists, and
    falls back to the original v1 30 frame classifier otherwise.
    """
    REQUIRED_RESOURCES = {"CAMERA", "SPEAKER"}

    def __init__(self):
        self.is_running = False
        self._thread = None
        self._stop_evt = threading.Event()
        self.streamer = None
        self.recognizer = None
        self.version = None
        self.on_prediction: Optional[Callable] = None
        self.on_prediction_detail: Optional[Callable] = None
        self.on_status: Optional[Callable] = None
        # v1 fallback members
        self.classifier = None
        self.extractor = None
        self.buffer = None

    def start(self, use_mock=False, video_path=None, **kwargs):
        if self.is_running:
            return
        # Optional callback(word, confidence) used by the web emulator
        self.on_prediction = kwargs.get("on_prediction")
        # Optional callback(details: dict) with every prediction (accepted or not, top 3)
        self.on_prediction_detail = kwargs.get("on_prediction_detail")
        # Optional callback(landmarks, recording) after every processed frame (v2 only)
        self.on_status = kwargs.get("on_status")
        print("[MUTE_PIPELINE] Starting Mute Mode sign language pipeline...")
        _ensure_headless_compat()
        from mute_mode.video_stream import VideoStreamer
        from mute_mode.recognizer import DEFAULT_CHECKPOINT

        self.streamer = kwargs.get("video_source") or VideoStreamer(video_path=video_path, use_mock=use_mock)
        if os.path.exists(DEFAULT_CHECKPOINT):
            from mute_mode.recognizer import LiveSignRecognizer
            self.recognizer = LiveSignRecognizer(DEFAULT_CHECKPOINT)
            self.version = "v2"
            # Warm up: MediaPipe initialises lazily and the first few calls are slow,
            # which used to swallow the first sign after switching to Mute Mode.
            import numpy as np
            blank = np.zeros((240, 320, 3), np.uint8)
            for i in range(3):
                self.recognizer.extractor.extract(blank, i)
        else:
            from mute_mode.train_classifier import load_checkpoint
            from mute_mode.landmark_extractor import LandmarkExtractor
            from mute_mode.sequence_buffer import GestureSequenceBuffer
            ckpt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mute_mode", "checkpoints", "final_model.pth"))
            self.classifier = load_checkpoint(ckpt)
            self.extractor = LandmarkExtractor()
            self.buffer = GestureSequenceBuffer()
            self.version = "v1"
        print(f"[MUTE_PIPELINE] Using sign recogniser {self.version}.")
        self._stop_evt.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop_wrapper, daemon=True, name="mute-loop")
        self._thread.start()

    def _announce(self, word, confidence):
        from shared.tts_output import speak
        print(f"[MUTE_PIPELINE] Predicted: {word.upper()} (conf: {confidence:.2f})")
        speak(word, cooldown=1.5)
        if self.on_prediction:
            self.on_prediction(word, float(confidence))

    def _run_loop_wrapper(self):
        while not self._stop_evt.is_set():
            ret, frame = self.streamer.read()
            if not ret or frame is None:
                self._stop_evt.wait(0.01)
                continue
            if self.version == "v2":
                pred = self.recognizer.process_frame(frame)
                if self.on_status:
                    self.on_status(self.recognizer.last_landmarks, self.recognizer.recording)
                if pred and self.on_prediction_detail:
                    self.on_prediction_detail(pred)
                if pred and pred["accepted"]:
                    self._announce(pred["label"], pred["confidence"])
            else:
                self._v1_step(frame)

    def _v1_step(self, frame):
        from mute_mode.classifier import extract_sequence_tensor
        self.buffer.add_frame(self.extractor.extract(frame))
        seq = self.buffer.get_sequence()
        if seq.get("buffer_full", False):
            pred = self.classifier.predict_step(extract_sequence_tensor(seq))
            if pred["confidence"] > 0.4:
                self._announce(pred["label"], pred["confidence"])
                self.buffer.clear()

    def stop(self):
        if not self.is_running:
            return
        print("[MUTE_PIPELINE] Stopping Mute Mode pipeline...")
        self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self.streamer:
            self.streamer.release()
            self.streamer = None
        for attr in ("recognizer", "extractor"):
            obj = getattr(self, attr)
            if obj is not None:
                obj.close()
                setattr(self, attr, None)
        self.is_running = False
        print("[MUTE_PIPELINE] Mute Mode stopped.")


class ModeManager:
    """
    TriSense System Mode Manager.
    Orchestrates exclusive mode transitions and resource safety.
    """
    def __init__(self):
        self.resource_guard = ResourceGuard()
        self.current_mode = "IDLE"
        # switch requests can arrive from the button, the keyboard and the web UI at once
        self._switch_lock = threading.RLock()
        self._pipelines = {
            "BLIND": BlindModePipeline(),
            "DEAF": DeafModePipeline(),
            "MUTE": MuteModePipeline()  # Extension point
        }
        start_tts_worker()

    def shutdown(self):
        """Stops the active pipeline and shuts down the shared TTS engine worker thread."""
        self.stop_current_mode()
        stop_tts_worker()

    def switch_mode(self, new_mode: str, **kwargs) -> bool:
        """
        Transitions the system to 'new_mode' ("IDLE", "BLIND", "DEAF", "MUTE").
        1. Stops the current active mode and releases all held hardware resources.
        2. Acquires required resources for 'new_mode'.
        3. Starts the target pipeline.
        """
        with self._switch_lock:
            return self._switch_mode_locked(new_mode, **kwargs)

    def _switch_mode_locked(self, new_mode: str, **kwargs) -> bool:
        new_mode = new_mode.upper()
        if new_mode == self.current_mode:
            print(f"[MODE_MANAGER] Already in mode '{self.current_mode}'. No transition needed.")
            return True

        if new_mode != "IDLE" and new_mode not in self._pipelines:
            raise ValueError(f"Unknown operational mode: '{new_mode}'. Valid modes: IDLE, BLIND, DEAF, MUTE.")

        print(f"\n[MODE_MANAGER] === Transitioning Mode: '{self.current_mode}' -> '{new_mode}' ===")
        
        # Step 1: Stop current mode and release resources
        self._stop_current_locked()

        # Step 2: If switching to IDLE, we are done
        if new_mode == "IDLE":
            self.current_mode = "IDLE"
            print("[MODE_MANAGER] System transitioned to IDLE mode.")
            return True

        # Step 3: Acquire resources for new mode
        pipeline = self._pipelines[new_mode]
        required_resources = pipeline.REQUIRED_RESOURCES
        self.resource_guard.acquire(new_mode, required_resources)

        # Step 4: Start target pipeline
        try:
            pipeline.start(**kwargs)
            self.current_mode = new_mode
            print(f"[MODE_MANAGER] Successfully switched to mode '{new_mode}'.\n")
            return True
        except NotImplementedError as ne:
            print(f"[MODE_MANAGER] Extension point alert: {ne}")
            self.resource_guard.release(new_mode)
            self.current_mode = "IDLE"
            return False
        except Exception as e:
            print(f"[MODE_MANAGER] Error starting mode '{new_mode}': {e}. Reverting to IDLE.")
            self.resource_guard.release(new_mode)
            self.current_mode = "IDLE"
            raise

    def stop_current_mode(self):
        """
        Stops whatever mode is currently running and releases its resources.
        """
        with self._switch_lock:
            self._stop_current_locked()

    def _stop_current_locked(self):
        if self.current_mode == "IDLE":
            return

        pipeline = self._pipelines.get(self.current_mode)
        if pipeline and pipeline.is_running:
            pipeline.stop()
        flush_tts()  # never read out stale phrases from the previous mode

        self.resource_guard.release(self.current_mode)
        print(f"[MODE_MANAGER] Mode '{self.current_mode}' deactivated.")
        self.current_mode = "IDLE"

    def handle_key_input(self, key: str, **kwargs) -> str:
        """
        Mock mode-switch trigger standing in for a physical GPIO button press.
        Maps key characters to operational mode transitions:
          '0' or 'q' -> IDLE
          '1'        -> BLIND
          '2'        -> DEAF
          '3'        -> MUTE (extension point)
        """
        key_map = {
            "0": "IDLE",
            "q": "IDLE",
            "Q": "IDLE",
            "1": "BLIND",
            "2": "DEAF",
            "3": "MUTE"
        }
        target_mode = key_map.get(key)
        if not target_mode:
            print(f"[MODE_MANAGER] Unmapped key '{key}'. Ignore.")
            return self.current_mode

        self.switch_mode(target_mode, **kwargs)
        return self.current_mode

    def get_pipeline(self, mode: str):
        return self._pipelines.get(mode.upper())
