# deaf_mode/test_asr_engine.py
# -----------------------------------------------------------------------------
# Standalone Verification Script for Step 1.2 (Vosk Offline Speech Recognizer).
# Tests:
# 1. ASREngine initialization and fallback mode detection.
# 2. Streaming WAV blocks from Step 1.1 into ASREngine.accept_waveform().
# 3. Live PartialResult extraction and utterance completion Result() JSON parsing.
# 4. FinalResult extraction at stream closure.
# -----------------------------------------------------------------------------

import os
import sys
import time

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.config import SAMPLE_RATE, BLOCK_SIZE, DEFAULT_SAMPLE_WAV
from deaf_mode.mock_audio import create_sample_wav, MockAudioStream
from deaf_mode.asr_engine import ASREngine


def run_test():
    print("=========================================================")
    print(" TriSense Deaf Mode — Step 1.2: Vosk ASR Verification")
    print("=========================================================\n")

    test_wav = "deaf_mode/real_speech.wav"
    if not os.path.exists(test_wav):
        create_sample_wav(test_wav, duration_s=3.0, sample_rate=SAMPLE_RATE)

    # 1. Initialize ASR Engine (uses real Vosk model by default if installed)
    print("1. Initializing ASREngine with real Vosk offline model...")
    asr = ASREngine(sample_rate=SAMPLE_RATE, use_mock=False)

    # 2. Stream audio blocks through ASR engine
    print(f"2. Feeding WAV audio blocks ({BLOCK_SIZE} frames per block) into ASREngine...")
    
    utterance_results = []
    partial_results = []
    total_blocks = 0
    start_time = time.time()

    def asr_stream_callback(indata, frames, time_info, status):
        nonlocal total_blocks
        total_blocks += 1
        
        # Feed waveform to recognizer
        is_utterance_complete = asr.accept_waveform(indata)
        
        # Capture partial while streaming
        partial_text = asr.get_partial_result()
        if partial_text and (not partial_results or partial_results[-1] != partial_text):
            partial_results.append(partial_text)
            print(f"   [PARTIAL] \"{partial_text}\"")
            
        # Capture full sentence if utterance completed
        if is_utterance_complete:
            sentence = asr.get_result()
            if sentence:
                utterance_results.append(sentence)
                print(f"   [COMPLETE RESULT] \"{sentence}\"")

    streamer = MockAudioStream(
        wav_path=test_wav,
        sample_rate=SAMPLE_RATE,
        block_size=BLOCK_SIZE,
        callback=asr_stream_callback,
        real_time=False
    )
    
    streamer.start()
    
    # Check final result at stream close
    final_sentence = asr.get_final_result()
    if final_sentence:
        utterance_results.append(final_sentence)
        print(f"   [FINAL RESULT] \"{final_sentence}\"")

    elapsed_ms = (time.time() - start_time) * 1000.0

    # 3. Assertions & Summary
    print("\n---------------------------------------------------------")
    print("Verification Summary:")
    print(f" - Engine Mode     : {'MockRecognizer (Headless/Fallback)' if asr.is_mock() else 'Vosk KaldiRecognizer (Offline Model)'}")
    print(f" - Blocks Processed: {total_blocks}")
    print(f" - Partials Seen   : {len(partial_results)}")
    print(f" - Sentences Recv  : {len(utterance_results)}")
    print(f" - Total Time (ms) : {elapsed_ms:.1f} ms")

    passed = True

    if total_blocks > 0:
        print(" [PASS] ASREngine successfully consumed audio waveform blocks.")
    else:
        print(" [FAIL] No audio blocks reached ASREngine.")
        passed = False

    if len(partial_results) > 0:
        print(f" [PASS] Live PartialResult text extracted while streaming ({len(partial_results)} updates).")
    else:
        print(" [FAIL] No partial transcription updates generated.")
        passed = False

    if len(utterance_results) > 0:
        print(f" [PASS] Utterance completion triggered valid Result() text: \"{utterance_results[0]}\"")
    else:
        print(" [FAIL] No final sentence transcriptions produced.")
        passed = False

    print("---------------------------------------------------------")
    if passed:
        print("RESULT: ALL STEP 1.2 TESTS PASSED [PASS]\n")
    else:
        print("RESULT: STEP 1.2 TEST FAILED [FAIL]\n")

    return passed


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
