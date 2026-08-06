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
from typing import Dict, Set, Optional


def _ensure_headless_compat():
    """Inject mock GPIO and mock TTS if running on a PC/headless environment without physical RPi.GPIO."""
    try:
        import RPi.GPIO
    except ImportError:
        mock_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "blind_mode", "mock_lib"))
        if mock_lib_path not in sys.path:
            sys.path.insert(0, mock_lib_path)
    try:
        import pyttsx3
    except (ImportError, OSError):
        import unittest.mock
        sys.modules['pyttsx3'] = unittest.mock.MagicMock()


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

    def clear(self):
        with self._lock:
            self._owners.clear()


class BlindModePipeline:
    """
    Adapter for Blind Mode (`blind_mode/sensor_loop.py`).
    Runs sensor polling, collision detection, and haptic/audio alerts without
    modifying `sensor_loop.py` internals.
    """
    REQUIRED_RESOURCES = {"SPEAKER", "GPIO_SENSORS", "GPIO_MOTORS"}

    def __init__(self):
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, **kwargs):
        if self.is_running:
            return
        print("[BLIND_PIPELINE] Starting Blind Mode ultrasonic/haptic pipeline...")
        _ensure_headless_compat()
        from blind_mode.gpio_setup import setup
        setup()
        self.is_running = True

        # Run sensor polling loop in background daemon thread
        self._thread = threading.Thread(target=self._run_loop_wrapper, daemon=True)
        self._thread.start()

    def _run_loop_wrapper(self):
        _ensure_headless_compat()
        from blind_mode.distance import read_all_sensors
        from blind_mode.collision import compute_closing_speed, time_to_collision
        from blind_mode.haptic import get_alert_intensity, pulse_motor
        from blind_mode.audio_alert import speak_alert, TTC_AUDIO_THRESHOLD_S
        from blind_mode.config import SENSORS, MOTORS

        prev_readings = read_all_sensors()
        while self.is_running:
            time.sleep(0.1)
            curr_readings = read_all_sensors()
            for label, _trig, _echo in SENSORS:
                d_a = prev_readings[label]
                d_b = curr_readings[label]
                speed = compute_closing_speed(d_a, d_b, 0.1)
                ttc = time_to_collision(d_b, speed)
                duration = get_alert_intensity(ttc, threshold=1.5)
                if duration is not None:
                    pin = MOTORS[label]
                    pulse_motor(pin, duration)
                if label == "center" and ttc is not None and ttc < TTC_AUDIO_THRESHOLD_S:
                    speak_alert("Obstacle ahead")
            prev_readings = curr_readings

    def stop(self):
        if not self.is_running:
            return
        print("[BLIND_PIPELINE] Stopping Blind Mode pipeline...")
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        from blind_mode.audio_alert import shutdown_audio
        from blind_mode.gpio_setup import cleanup
        shutdown_audio()
        cleanup()
        print("[BLIND_PIPELINE] Blind Mode stopped and GPIO released.")


class DeafModePipeline:
    """
    Adapter for Deaf Mode (`deaf_mode/main_loop.py`).
    Wraps DeafModeApp without modifying internal ASR or OLED modules.
    """
    REQUIRED_RESOURCES = {"MICROPHONE", "DISPLAY"}

    def __init__(self):
        self.is_running = False
        self.app = None
        self.summary = None

    def start(self, wav_path=None, use_mock=True, **kwargs):
        if self.is_running:
            return
        print("[DEAF_PIPELINE] Starting Deaf Mode speech-to-text pipeline...")
        from deaf_mode.audio_stream import AudioStreamer
        from deaf_mode.asr_engine import ASREngine
        from deaf_mode.caption_formatter import CaptionFormatter
        from deaf_mode.oled_display import OLEDDisplay
        from deaf_mode.caption_renderer import CaptionRenderer
        from deaf_mode.main_loop import DeafModeApp

        audio_streamer = AudioStreamer(callback=None, sample_rate=16000, block_size=4000,
                                       wav_path=wav_path, use_mock=use_mock)
        asr_engine = ASREngine(sample_rate=16000, use_mock=not bool(wav_path) and use_mock)
        formatter = CaptionFormatter(max_chars_per_line=20, max_lines=3)
        display = OLEDDisplay(width=128, height=64, use_mock=True)
        renderer = CaptionRenderer(display=display, formatter=formatter, default_header="TriSense ASR [REC]")

        self.app = DeafModeApp(
            audio_streamer=audio_streamer,
            asr_engine=asr_engine,
            renderer=renderer,
            on_caption_update=kwargs.get("on_caption_update")
        )
        self.is_running = True
        # Run synchronous stream or launch background execution
        self.summary = self.app.run(real_time=False)

    def stop(self):
        if not self.is_running:
            return
        print("[DEAF_PIPELINE] Stopping Deaf Mode pipeline...")
        self.is_running = False
        if self.app:
            self.app.close()
        print("[DEAF_PIPELINE] Deaf Mode stopped.")


class MuteModePipeline:
    """
    EXTENSION POINT: Mute Mode (Sign Language Recognition -> Speech).
    Uses camera input and speaker output.
    """
    REQUIRED_RESOURCES = {"CAMERA", "SPEAKER"}

    def __init__(self):
        self.is_running = False
        self._thread = None
        self.classifier = None
        self.streamer = None
        self.extractor = None
        self.buffer = None

    def start(self, use_mock=False, **kwargs):
        if self.is_running:
            return
        print("[MUTE_PIPELINE] Starting Mute Mode sign language pipeline...")
        _ensure_headless_compat()

        from mute_mode.train_classifier import load_checkpoint
        from mute_mode.video_stream import VideoStreamer
        from mute_mode.landmark_extractor import LandmarkExtractor
        from mute_mode.sequence_buffer import GestureSequenceBuffer

        checkpoint_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mute_mode", "checkpoints", "final_model.pth"))
        self.classifier = load_checkpoint(checkpoint_path)
        self.streamer = VideoStreamer(use_mock=use_mock)
        self.extractor = LandmarkExtractor()
        self.buffer = GestureSequenceBuffer()
        
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop_wrapper, daemon=True)
        self._thread.start()

    def _run_loop_wrapper(self):
        from mute_mode.classifier import extract_sequence_tensor
        from blind_mode.audio_alert import speak_alert
        
        while self.is_running:
            time.sleep(0.01)
            ret, frame = self.streamer.read()
            if not ret or frame is None:
                continue

            extraction = self.extractor.extract(frame)
            self.buffer.add_frame(extraction)
            
            seq = self.buffer.get_sequence()
            if seq.get("buffer_full", False):
                tensor = extract_sequence_tensor(seq)
                pred = self.classifier.predict_step(tensor)
                
                if pred["confidence"] > 0.4:
                    word = pred["label"]
                    print(f"[MUTE_PIPELINE] Predicted: {word.upper()} (conf: {pred['confidence']:.2f})")
                    speak_alert(word, cooldown=2.0)
                    self.buffer.clear()

    def stop(self):
        if not self.is_running:
            return
        print("[MUTE_PIPELINE] Stopping Mute Mode pipeline...")
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        
        if self.streamer:
            self.streamer.release()
            self.streamer = None
        if self.extractor:
            self.extractor.close()
            self.extractor = None
        
        print("[MUTE_PIPELINE] Mute Mode stopped.")


class ModeManager:
    """
    TriSense System Mode Manager.
    Orchestrates exclusive mode transitions and resource safety.
    """
    def __init__(self):
        self.resource_guard = ResourceGuard()
        self.current_mode = "IDLE"
        self._pipelines = {
            "BLIND": BlindModePipeline(),
            "DEAF": DeafModePipeline(),
            "MUTE": MuteModePipeline()  # Extension point
        }

    def switch_mode(self, new_mode: str, **kwargs) -> bool:
        """
        Transitions the system to 'new_mode' ("IDLE", "BLIND", "DEAF", "MUTE").
        1. Stops the current active mode and releases all held hardware resources.
        2. Acquires required resources for 'new_mode'.
        3. Starts the target pipeline.
        """
        new_mode = new_mode.upper()
        if new_mode == self.current_mode:
            print(f"[MODE_MANAGER] Already in mode '{self.current_mode}'. No transition needed.")
            return True

        if new_mode != "IDLE" and new_mode not in self._pipelines:
            raise ValueError(f"Unknown operational mode: '{new_mode}'. Valid modes: IDLE, BLIND, DEAF, MUTE.")

        print(f"\n[MODE_MANAGER] === Transitioning Mode: '{self.current_mode}' -> '{new_mode}' ===")
        
        # Step 1: Stop current mode and release resources
        self.stop_current_mode()

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
        if self.current_mode == "IDLE":
            return

        pipeline = self._pipelines.get(self.current_mode)
        if pipeline and pipeline.is_running:
            pipeline.stop()

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
