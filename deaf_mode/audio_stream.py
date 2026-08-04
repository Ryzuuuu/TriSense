# deaf_mode/audio_stream.py
# -----------------------------------------------------------------------------
# Unified Audio Stream Abstraction for TriSense Deaf Mode.
# Connects to either a real INMP441 I2S microphone (via sounddevice) on Pi
# hardware, or to MockAudioStream (reading .wav files) during headless/PC
# software validation.
# -----------------------------------------------------------------------------

import time
from .config import SAMPLE_RATE, CHANNELS, BLOCK_SIZE, DTYPE, MOCK_AUDIO
from .mock_audio import MockAudioStream

# Try importing sounddevice; fall back to mock if unavailable
try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except (ImportError, OSError):
    _HAS_SOUNDDEVICE = False


class AudioStreamer:
    """
    Unified audio input interface.
    
    Parameters:
      callback: function(indata, frames, time_info, status)
                Called repeatedly with audio buffer chunks of size block_size.
      use_mock: bool
                If True, uses MockAudioStream. Otherwise uses sounddevice.
      wav_path: str (optional)
                Path to a .wav file to stream when use_mock=True.
    """
    def __init__(self, callback, sample_rate=SAMPLE_RATE, channels=CHANNELS,
                 block_size=BLOCK_SIZE, dtype=DTYPE, use_mock=MOCK_AUDIO, wav_path=None):
        self.callback = callback
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.dtype = dtype
        self.wav_path = wav_path
        self.use_mock = use_mock or (not _HAS_SOUNDDEVICE)
        
        if self.wav_path:
            self.mode = "WAVFileStream"
        elif self.use_mock:
            self.mode = "MockAudioStream"
        else:
            self.mode = "HardwareMicrophone"
        
        self._stream = None
        self._is_active = False

    def start(self, real_time=False):
        """Starts capturing or streaming audio blocks to the callback."""
        if self._is_active:
            return

        if self.use_mock:
            print(f"[AUDIO_STREAM] Starting MockAudioStream (WAV: {self.wav_path or 'Synthetic PCM'})...")
            self._stream = MockAudioStream(
                wav_path=self.wav_path,
                sample_rate=self.sample_rate,
                block_size=self.block_size,
                callback=self.callback,
                real_time=real_time
            )
            self._is_active = True
            self._stream.start()
            self._is_active = False
        else:
            print("[AUDIO_STREAM] Starting sounddevice RawInputStream (Hardware Mic)...")
            try:
                self._stream = sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    dtype=self.dtype,
                    channels=self.channels,
                    callback=self.callback
                )
                self._stream.start()
                self._is_active = True
            except Exception as e:
                print(f"[AUDIO_STREAM] Hardware audio initialization error: {e}. Falling back to MockAudioStream.")
                self.use_mock = True
                self.mode = "MockAudioStream"
                self.start(real_time=real_time)

    def stop(self):
        """Stops the audio stream cleanly."""
        if self._stream and self._is_active:
            self._stream.stop()
            if not self.use_mock and hasattr(self._stream, "close"):
                self._stream.close()
        self._is_active = False
        print("[AUDIO_STREAM] Audio stream stopped.")

    def is_active(self):
        return self._is_active
