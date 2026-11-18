# deaf_mode/config.py
# -----------------------------------------------------------------------------
# Configuration parameters for TriSense Deaf Mode (Offline ASR & Captions).
# -----------------------------------------------------------------------------
import os

# --- Audio Input Settings (Matched to Vosk's native requirement) ---
SAMPLE_RATE = 16000          # 16 kHz sample rate required by Vosk small-en-us
CHANNELS = 1                 # Mono microphone input
BLOCK_SIZE = 4000            # Number of frames per buffer chunk (0.25s latency block)
DTYPE = "int16"              # 16-bit signed integer PCM

# --- Mode & Environment Override ---
# Set TRISENSE_MOCK_AUDIO=0 in environment to force hardware microphone input
# "1" forces the WAV/synthetic mock, "0" forces the microphone. Default: mock
# (the desktop tests and emulator rely on it); the Pi service sets it to "0".
MOCK_AUDIO = os.getenv("TRISENSE_MOCK_AUDIO", "1") == "1"

# --- ASR Engine Settings ---
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Absolute by default so the model is found no matter which directory the app is started from.
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", os.path.join(_REPO_ROOT, "models", "vosk-model-small-en-us"))
# Use the real Vosk recogniser whenever the model is present, unless TRISENSE_ASR_MOCK=1.
ASR_MOCK = os.getenv("TRISENSE_ASR_MOCK", "0") == "1"

# --- Default paths ---
DEFAULT_SAMPLE_WAV = "deaf_mode/sample_test.wav"
