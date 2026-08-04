# deaf_mode/mock_audio.py
# -----------------------------------------------------------------------------
# Headless Mock Audio Helper Layer for TriSense Deaf Mode.
# Streams 16-bit PCM mono audio chunks from a .wav file or generates synthetic
# test PCM data so the ASR pipeline can be tested without physical microphone
# hardware or Raspberry Pi I2S wiring.
# -----------------------------------------------------------------------------

import wave
import struct
import math
import time
import os
from .config import SAMPLE_RATE, CHANNELS, BLOCK_SIZE


def create_sample_wav(filename, duration_s=3.0, frequency=440.0, sample_rate=SAMPLE_RATE):
    """
    Generates a sample 16 kHz 16-bit mono WAV file for verification testing.
    Produces a gentle modulated sine wave tone simulating audio input frames.
    """
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    num_samples = int(duration_s * sample_rate)
    
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)      # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        
        for i in range(num_samples):
            # Gentle amplitude-modulated sine wave
            t = float(i) / sample_rate
            value = int(10000 * math.sin(2.0 * math.pi * frequency * t) * (1.0 + 0.5 * math.sin(2.0 * math.pi * 2.0 * t)))
            # Clamp to 16-bit signed int range [-32768, 32767]
            value = max(-32768, min(32767, value))
            data = struct.pack("<h", value)
            wf.writeframesraw(data)
            
    return filename


class MockAudioStream:
    """
    Simulates a sounddevice input stream by reading a WAV file (or synthetic PCM)
    and invoking a callback function with byte chunks of size BLOCK_SIZE frames.
    """
    def __init__(self, wav_path=None, sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE, callback=None, real_time=False):
        self.wav_path = wav_path
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.callback = callback
        self.real_time = real_time
        self._running = False
        self._frames_streamed = 0
        self._wf = None

    def start(self):
        """Opens WAV file and starts streaming chunks to callback."""
        self._running = True
        self._frames_streamed = 0
        
        if self.wav_path and os.path.exists(self.wav_path):
            self._stream_wav()
        else:
            self._stream_synthetic()

    def _stream_wav(self):
        with wave.open(self.wav_path, "rb") as wf:
            self._wf = wf
            n_channels = wf.getnchannels()
            samp_width = wf.getsampwidth()
            framerate = wf.getframerate()
            
            if framerate != self.sample_rate or samp_width != 2:
                print(f"[WARN] WAV format ({framerate}Hz, width={samp_width}) differs from expected ({self.sample_rate}Hz, 16-bit).")
                
            bytes_per_frame = samp_width * n_channels
            chunk_bytes = self.block_size * bytes_per_frame
            
            while self._running:
                raw_data = wf.readframes(self.block_size)
                if not raw_data:
                    break   # End of file reached
                    
                frames_read = len(raw_data) // bytes_per_frame
                self._frames_streamed += frames_read
                
                if self.callback:
                    # Match sounddevice callback signature: (indata, frames, time, status)
                    self.callback(raw_data, frames_read, time.time(), None)
                    
                if self.real_time:
                    time.sleep(frames_read / float(self.sample_rate))
                    
        self._running = False

    def _stream_synthetic(self):
        """Generates 4 silent/test chunks if no file is provided."""
        num_chunks = 4
        chunk_data = b"\x00\x00" * self.block_size
        for _ in range(num_chunks):
            if not self._running:
                break
            self._frames_streamed += self.block_size
            if self.callback:
                self.callback(chunk_data, self.block_size, time.time(), None)
            if self.real_time:
                time.sleep(self.block_size / float(self.sample_rate))
        self._running = False

    def stop(self):
        """Stops the audio stream."""
        self._running = False

    def is_active(self):
        return self._running

    def get_total_frames(self):
        return self._frames_streamed
