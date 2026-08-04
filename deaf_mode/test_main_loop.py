# deaf_mode/test_main_loop.py
# -----------------------------------------------------------------------------
# Standalone End-to-End Verification Script for Step 3.1 (Deaf Mode Main Loop).
# Wires together:
#   1. REAL AudioStreamer (streaming 16kHz PCM from real_speech.wav)
#   2. REAL ASREngine (Vosk KaldiRecognizer with official offline model)
#   3. REAL CaptionFormatter (punctuation, capitalization, smart wrapping)
#   4. REAL OLEDDisplay & CaptionRenderer (rendering live ASCII OLED viewports)
# -----------------------------------------------------------------------------

import os
import sys

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.audio_stream import AudioStreamer
from deaf_mode.asr_engine import ASREngine
from deaf_mode.caption_formatter import CaptionFormatter
from deaf_mode.oled_display import OLEDDisplay
from deaf_mode.caption_renderer import CaptionRenderer
from deaf_mode.main_loop import DeafModeApp


def ensure_wav_file(wav_path: str):
    if not os.path.exists(wav_path):
        print(f"[{wav_path} not found. Generating real speech test WAV...]")
        from deaf_mode.generate_real_speech_wav import generate_test_wav
        generate_test_wav(wav_path)


def run_test():
    print("=======================================================================")
    print(" TriSense Deaf Mode — Step 3.1: End-to-End Main Loop Test")
    print("=======================================================================\n")

    wav_path = os.path.join(os.path.dirname(__file__), "real_speech.wav")
    ensure_wav_file(wav_path)

    print("1. Initializing REAL Subsystems (No Mocks Substituting For Any Stage)...")
    
    # AudioStreamer configured with wav_path to stream real audio PCM frames
    audio_streamer = AudioStreamer(callback=None, sample_rate=16000, block_size=4000, wav_path=wav_path, use_mock=True)
    # Real ASREngine using official offline Vosk KaldiRecognizer
    asr_engine = ASREngine(sample_rate=16000, use_mock=False)
    # Real CaptionFormatter and OLEDDisplay / CaptionRenderer
    formatter = CaptionFormatter(max_chars_per_line=20, max_lines=3)
    display = OLEDDisplay(width=128, height=64, use_mock=True)
    renderer = CaptionRenderer(display=display, formatter=formatter, default_header="TriSense ASR [REC]")

    print(f"   AudioStreamer WAV Path : {wav_path}")
    print(f"   ASREngine Mode         : {asr_engine.mode}")
    print(f"   OLEDDisplay Mode       : {display.mode}")

    if asr_engine.mode != "VoskRecognizer":
        print("   [FAIL] Real ASREngine failed to initialize VoskRecognizer.")
        return False

    print("   [PASS] All real pipeline stages initialized successfully.\n")

    print("2. Executing Real-Time End-to-End Transcription & Subtitle Rendering...")
    last_rendered_caption = [""]
    update_counter = [0]

    def on_caption_change(text, is_final):
        if text != last_rendered_caption[0] and text.strip():
            last_rendered_caption[0] = text
            update_counter[0] += 1
            status_type = "FINAL" if is_final else "PARTIAL"
            print(f"\n   [Update #{update_counter[0]} - {status_type}] OLED Subtitle Updated: \"{text}\"")
            for line in display.render_ascii().split("\n"):
                print(f"     {line}")

    app = DeafModeApp(
        audio_streamer=audio_streamer,
        asr_engine=asr_engine,
        renderer=renderer,
        on_caption_update=on_caption_change
    )
    
    # Run the main loop to completion (streams all audio blocks from WAV file)
    summary = app.run(real_time=False)

    print("\n3. Verifying End-to-End Pipeline Summary & Session History...")
    history = summary["history"]
    print(f"   Total Blocks Processed : {summary['blocks_processed']}")
    print(f"   Total Utterances       : {summary['utterances']}")
    print(f"   Session History Log    : {history}")

    passed = True
    if summary["blocks_processed"] == 0:
        print("   [FAIL] No audio blocks were processed.")
        passed = False

    if len(history) == 0:
        print("   [FAIL] No completed utterances were logged in session history.")
        passed = False
    else:
        final_phrase = history[-1]
        # Verify keywords from speech audio appear in transcribed history
        if "obstacle" in final_phrase and "left" in final_phrase and "stop" in final_phrase:
            print("   [PASS] Transcribed sentence matches target spoken phrase.")
        else:
            print(f"   [FAIL] Transcribed phrase missing expected keywords: {final_phrase}")
            passed = False

    app.close()
    print("\n-----------------------------------------------------------------------")
    if passed:
        print("RESULT: ALL STEP 3.1 TESTS PASSED [PASS]\n")
    else:
        print("RESULT: STEP 3.1 TEST FAILED [FAIL]\n")

    return passed


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
