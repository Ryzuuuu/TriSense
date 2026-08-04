# deaf_mode/asr_engine.py
# -----------------------------------------------------------------------------
# Offline Speech Recognition Engine Wrapper for TriSense Deaf Mode.
# Wraps Vosk offline recognizer (KaldiRecognizer) and provides a MockRecognizer
# fallback when Vosk library or local model directory is unavailable during
# software validation.
# -----------------------------------------------------------------------------

import os
import json
import struct
import math
from .config import SAMPLE_RATE, VOSK_MODEL_PATH, ASR_MOCK

try:
    import vosk
    _HAS_VOSK = True
except ImportError:
    _HAS_VOSK = False


class MockRecognizer:
    """
    Simulates vosk.KaldiRecognizer for headless software verification.
    Produces partial and final JSON transcription strings matching Vosk schema.
    """
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.chunks_processed = 0
        self._current_utterance = ""
        self._partial = ""
        self._vocabulary = [
            "hello trisense",
            "obstacle ahead left",
            "system ready for captioning",
            "deaf mode speech verification"
        ]

    def AcceptWaveform(self, data: bytes) -> bool:
        """
        Receives raw 16-bit PCM bytes. Returns True when an utterance completes.
        """
        self.chunks_processed += 1
        
        # Calculate RMS energy to detect non-silence
        num_samples = len(data) // 2
        if num_samples > 0:
            samples = struct.unpack(f"<{num_samples}h", data)
            rms = math.sqrt(sum(s * s for s in samples) / num_samples)
        else:
            rms = 0.0

        if rms > 500.0:
            # Simulate speech progress through vocabulary list
            vocab_index = (self.chunks_processed // 4) % len(self._vocabulary)
            target_phrase = self._vocabulary[vocab_index]
            words = target_phrase.split()
            word_count = min(len(words), (self.chunks_processed % 4) + 1)
            self._partial = " ".join(words[:word_count])
            self._current_utterance = target_phrase
        else:
            self._partial = ""

        # Trigger completed utterance result every 4 audio blocks (~1.0s)
        if self.chunks_processed % 4 == 0 and self._current_utterance:
            return True
        return False

    def Result(self) -> str:
        """Returns JSON containing the recognized text of the utterance."""
        res = {"text": self._current_utterance}
        self._current_utterance = ""
        self._partial = ""
        return json.dumps(res)

    def PartialResult(self) -> str:
        """Returns JSON containing live partial text recognition."""
        return json.dumps({"partial": self._partial})

    def FinalResult(self) -> str:
        """Returns JSON containing remaining recognized text at stream close."""
        res = {"text": self._current_utterance}
        self._current_utterance = ""
        self._partial = ""
        return json.dumps(res)

    def Reset(self):
        self.chunks_processed = 0
        self._current_utterance = ""
        self._partial = ""


class ASREngine:
    """
    Unified Offline ASR Interface for Deaf Mode.
    
    Parameters:
      model_path : str
                   Path to Vosk language model directory (e.g., 'models/vosk-model-small-en-us')
      sample_rate: int
                   Audio sample rate in Hz (default 16000)
      use_mock   : bool
                   If True, forces MockRecognizer. Otherwise uses Vosk if available.
    """
    def __init__(self, model_path=VOSK_MODEL_PATH, sample_rate=SAMPLE_RATE, use_mock=None):
        self.model_path = model_path
        self.sample_rate = sample_rate
        
        if use_mock is None:
            self.use_mock = ASR_MOCK or (not _HAS_VOSK) or (not os.path.exists(self.model_path))
        else:
            self.use_mock = use_mock
            
        self.recognizer = None
        self._init_engine()

    def _init_engine(self):
        if self.use_mock:
            print(f"[ASR_ENGINE] Using MockRecognizer (Vosk available: {_HAS_VOSK}, Model path: '{self.model_path}').")
            self.recognizer = MockRecognizer(sample_rate=self.sample_rate)
        else:
            print(f"[ASR_ENGINE] Loading Vosk offline model from '{self.model_path}'...")
            try:
                vosk.SetLogLevel(-1)  # Silence verbose Kaldi logs
                model = vosk.Model(self.model_path)
                self.recognizer = vosk.KaldiRecognizer(model, self.sample_rate)
                print("[ASR_ENGINE] Vosk KaldiRecognizer initialized successfully.")
            except Exception as e:
                print(f"[ASR_ENGINE] Error loading Vosk model '{self.model_path}': {e}. Falling back to MockRecognizer.")
                self.use_mock = True
                self.recognizer = MockRecognizer(sample_rate=self.sample_rate)

    def accept_waveform(self, data: bytes) -> bool:
        """
        Feeds raw 16-bit mono PCM bytes to the ASR recognizer.
        Returns True if a complete sentence/utterance is recognized and ready in get_result().
        """
        return self.recognizer.AcceptWaveform(data)

    def get_result(self) -> str:
        """Returns recognized sentence text string."""
        raw_json = self.recognizer.Result()
        try:
            return json.loads(raw_json).get("text", "")
        except Exception:
            return ""

    def get_partial_result(self) -> str:
        """Returns in-progress partial transcription string."""
        raw_json = self.recognizer.PartialResult()
        try:
            return json.loads(raw_json).get("partial", "")
        except Exception:
            return ""

    def get_final_result(self) -> str:
        """Returns final remaining text string when stream ends."""
        raw_json = self.recognizer.FinalResult()
        try:
            return json.loads(raw_json).get("text", "")
        except Exception:
            return ""

    def reset(self):
        """Resets the recognizer buffer state."""
        if hasattr(self.recognizer, "Reset"):
            self.recognizer.Reset()

    def is_mock(self) -> bool:
        return self.use_mock
