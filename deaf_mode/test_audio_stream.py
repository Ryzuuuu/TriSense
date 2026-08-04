# deaf_mode/test_audio_stream.py
# -----------------------------------------------------------------------------
# Standalone Verification Script for Step 1.1 (Audio Input Abstraction).
# Tests:
# 1. WAV helper file generation (16 kHz, 16-bit mono PCM).
# 2. AudioStreamer streaming blocks in Mock mode.
# 3. Callback execution, frame count verification, and clean shutdown.
# -----------------------------------------------------------------------------

import os
import sys
import struct
import math

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.config import SAMPLE_RATE, BLOCK_SIZE, DEFAULT_SAMPLE_WAV
from deaf_mode.mock_audio import create_sample_wav
from deaf_mode.audio_stream import AudioStreamer


def run_test():
    print("=========================================================")
    print(" TriSense Deaf Mode — Step 1.1: Audio Stream Verification")
    print("=========================================================\n")

    test_wav = DEFAULT_SAMPLE_WAV
    duration_s = 2.0
    expected_total_frames = int(duration_s * SAMPLE_RATE)

    # 1. Create test WAV file
    print(f"1. Generating sample test WAV file: '{test_wav}' ({duration_s}s, {SAMPLE_RATE} Hz)...")
    create_sample_wav(test_wav, duration_s=duration_s, frequency=440.0, sample_rate=SAMPLE_RATE)
    
    if os.path.exists(test_wav) and os.path.getsize(test_wav) > 0:
        print("   [PASS] Sample WAV generated successfully.")
    else:
        print("   [FAIL] Failed to generate sample WAV file.")
        return False

    # 2. Track callback invocations and signal energy
    chunks_received = 0
    total_frames_received = 0
    energy_sum = 0.0

    def test_callback(indata, frames, time_info, status):
        nonlocal chunks_received, total_frames_received, energy_sum
        chunks_received += 1
        total_frames_received += frames
        
        # Calculate approximate signal energy (RMS) from 16-bit PCM bytes
        num_samples = len(indata) // 2
        samples = struct.unpack(f"<{num_samples}h", indata)
        chunk_sq_sum = sum(s * s for s in samples)
        energy_sum += chunk_sq_sum

    # 3. Initialize AudioStreamer in mock mode
    print("\n2. Initializing AudioStreamer in mock mode (reading WAV)...")
    streamer = AudioStreamer(
        callback=test_callback,
        sample_rate=SAMPLE_RATE,
        block_size=BLOCK_SIZE,
        use_mock=True,
        wav_path=test_wav
    )

    # 4. Execute stream
    print("3. Streaming audio blocks through callback...")
    streamer.start(real_time=False)
    streamer.stop()

    # 5. Assertions
    print("\n---------------------------------------------------------")
    print("Verification Summary:")
    print(f" - Sample Rate: {SAMPLE_RATE} Hz")
    print(f" - Block Size : {BLOCK_SIZE} frames ({BLOCK_SIZE / SAMPLE_RATE:.2f}s per chunk)")
    print(f" - Chunks Recv: {chunks_received}")
    print(f" - Total Frames: {total_frames_received} (Expected ~{expected_total_frames})")

    passed = True

    if chunks_received > 0:
        print(" [PASS] Callback invoked for every streamed block.")
    else:
        print(" [FAIL] Callback was never invoked.")
        passed = False

    if total_frames_received == expected_total_frames:
        print(" [PASS] Total frame count matches exact duration.")
    else:
        print(f" [FAIL] Frame count mismatch: {total_frames_received} != {expected_total_frames}")
        passed = False

    rms = math.sqrt(energy_sum / max(1, total_frames_received))
    if rms > 100.0:
        print(f" [PASS] Valid PCM audio amplitude detected (RMS = {rms:.1f}).")
    else:
        print(f" [FAIL] Audio appears silent or corrupted (RMS = {rms:.1f}).")
        passed = False

    print("---------------------------------------------------------")
    if passed:
        print("RESULT: ALL STEP 1.1 TESTS PASSED [PASS]\n")
    else:
        print("RESULT: STEP 1.1 TEST FAILED [FAIL]\n")

    return passed


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
