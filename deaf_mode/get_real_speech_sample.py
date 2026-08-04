# deaf_mode/get_real_speech_sample.py
# -----------------------------------------------------------------------------
# Downloads a real human speech recording and converts/resamples it to
# 16000 Hz 16-bit mono PCM WAV format for authentic offline Vosk ASR testing.
# -----------------------------------------------------------------------------

import os
import sys
import wave
import struct
import urllib.request

# Public domain human speech recording (Preamble of US Constitution)
PUBLIC_SPEECH_URL = "https://www2.cs.uic.edu/~i101/SoundFiles/preamble10.wav"
OUTPUT_WAV = "deaf_mode/real_speech.wav"
TEMP_RAW = "deaf_mode/raw_download.wav"


def resample_pcm_16bit_mono(samples, orig_rate, target_rate=16000):
    """Linear interpolation resampler for 16-bit mono PCM samples."""
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


def get_real_speech_wav(target_path=OUTPUT_WAV):
    os.makedirs(os.path.dirname(target_path) if os.path.dirname(target_path) else ".", exist_ok=True)
    
    print(f"[SPEECH_DL] Downloading real human speech sample from URL:\n  {PUBLIC_SPEECH_URL} ...")
    try:
        urllib.request.urlretrieve(PUBLIC_SPEECH_URL, TEMP_RAW)
    except Exception as e:
        print(f"[ERROR] Failed to download speech sample: {e}")
        return None

    if not os.path.exists(TEMP_RAW):
        print("[ERROR] Downloaded temporary file missing.")
        return None

    print(f"[SPEECH_DL] Converting downloaded audio to 16 kHz 16-bit mono PCM...")
    try:
        with wave.open(TEMP_RAW, "rb") as wf_in:
            n_channels = wf_in.getnchannels()
            sampwidth = wf_in.getsampwidth()
            framerate = wf_in.getframerate()
            raw_bytes = wf_in.readframes(wf_in.getnframes())
            
        num_samples = len(raw_bytes) // sampwidth
        
        if sampwidth == 2:
            samples = struct.unpack(f"<{num_samples}h", raw_bytes)
        elif sampwidth == 1:
            # 8-bit unsigned PCM -> 16-bit signed
            samples = [(b - 128) * 256 for b in raw_bytes]
        else:
            print(f"[ERROR] Unsupported sample width: {sampwidth}")
            return None

        if n_channels == 2:
            mono_samples = [(samples[i] + samples[i+1]) // 2 for i in range(0, len(samples), 2)]
        else:
            mono_samples = list(samples)

        target_samples = resample_pcm_16bit_mono(mono_samples, framerate, 16000)
        out_bytes = struct.pack(f"<{len(target_samples)}h", *target_samples)

        with wave.open(target_path, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(16000)
            wf_out.writeframes(out_bytes)

        if os.path.exists(TEMP_RAW):
            os.remove(TEMP_RAW)

        print(f"[SPEECH_DL] Authentic human speech WAV ready at: '{target_path}' ({len(target_samples)/16000.0:.2f}s) [PASS]")
        return target_path

    except Exception as e:
        print(f"[ERROR] Audio processing failed: {e}")
        if os.path.exists(TEMP_RAW):
            os.remove(TEMP_RAW)
        return None


if __name__ == "__main__":
    result = get_real_speech_wav()
    sys.exit(0 if result else 1)
