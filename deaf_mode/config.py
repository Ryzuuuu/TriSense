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
MOCK_AUDIO = os.getenv("TRISENSE_MOCK_AUDIO", "1") == "1"

# --- ASR Engine Settings ---
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-en-us")
ASR_MOCK = os.getenv("TRISENSE_ASR_MOCK", "1") == "1"

# --- Default paths ---
DEFAULT_SAMPLE_WAV = "deaf_mode/sample_test.wav"
