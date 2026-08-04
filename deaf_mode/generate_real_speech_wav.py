# deaf_mode/generate_real_speech_wav.py
# -----------------------------------------------------------------------------
# Generates a sample real speech WAV file (16 kHz, 16-bit mono PCM) using
# Windows built-in speech synthesis (pyttsx3 / SAPI5) so that real offline
# speech recognition (Vosk) can be benchmarked against human speech.
# -----------------------------------------------------------------------------

import os
import sys
import wave
import struct

try:
    import pyttsx3
    _HAS_PYTTSX3 = True
except ImportError:
    _HAS_PYTTSX3 = False


def resample_pcm_16bit_mono(samples, orig_rate, target_rate=16000):
    """Simple linear interpolation resampler for 16-bit mono PCM samples."""
    if orig_rate == target_rate:
        return samples
    duration = len(samples) / float(orig_rate)
    target_len = int(duration * target_rate)
    resampled = []
    ratio = float(orig_rate) / float(target_rate)
    for i in range(target_len):
        src_idx = i * ratio
        idx0 = int(src_idx)
        idx1 = min(idx0 + 1, len(samples) - 1)
        frac = src_idx - idx0
        val = samples[idx0] * (1.0 - frac) + samples[idx1] * frac
        resampled.append(int(max(-32768, min(32767, val))))
    return resampled


def create_real_speech_wav(filename="deaf_mode/real_speech.wav",
                           text="hello trisense team an obstacle is ahead on your left please stop now"):
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    temp_wav = filename + ".tmp.wav"
    
    if not _HAS_PYTTSX3:
        print("[ERROR] pyttsx3 is required to generate synthetic human speech.")
        return None

    print(f"[SPEECH_GEN] Generating spoken text: \"{text}\"...")
    engine = pyttsx3.init()
    engine.setProperty("rate", 140)  # Clean speaking rate
    engine.save_to_file(text, temp_wav)
    engine.runAndWait()
    
    if not os.path.exists(temp_wav):
        print("[ERROR] Failed to save speech audio to temporary file.")
        return None

    print(f"[SPEECH_GEN] Reading temporary speech audio and converting to 16 kHz 16-bit mono PCM...")
    with wave.open(temp_wav, "rb") as wf_in:
        n_channels = wf_in.getnchannels()
        sampwidth = wf_in.getsampwidth()
        framerate = wf_in.getframerate()
        raw_bytes = wf_in.readframes(wf_in.getnframes())

    num_samples = len(raw_bytes) // sampwidth
    
    # Unpack 16-bit integers
    if sampwidth == 2:
        samples = struct.unpack(f"<{num_samples}h", raw_bytes)
    else:
        print(f"[ERROR] Unsupported sample width: {sampwidth}")
        return None

    # Convert stereo to mono by averaging left and right channels
    if n_channels == 2:
        mono_samples = [(samples[i] + samples[i+1]) // 2 for i in range(0, len(samples), 2)]
    elif n_channels == 1:
        mono_samples = list(samples)
    else:
        print(f"[ERROR] Unsupported channel count: {n_channels}")
        return None

    # Resample to 16000 Hz if needed
    target_samples = resample_pcm_16bit_mono(mono_samples, framerate, 16000)
    
    # Pack to 16-bit mono bytes
    out_bytes = struct.pack(f"<{len(target_samples)}h", *target_samples)

    with wave.open(filename, "wb") as wf_out:
        wf_out.setnchannels(1)
        wf_out.setsampwidth(2)
        wf_out.setframerate(16000)
        wf_out.writeframes(out_bytes)

    if os.path.exists(temp_wav):
        os.remove(temp_wav)

    print(f"[SPEECH_GEN] Spoken WAV sample ready at: '{filename}' ({len(target_samples)/16000.0:.2f}s) [PASS]")
    return filename


if __name__ == "__main__":
    out_file = create_real_speech_wav()
    sys.exit(0 if out_file else 1)
