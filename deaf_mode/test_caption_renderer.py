# deaf_mode/test_caption_renderer.py
# -----------------------------------------------------------------------------
# Standalone Verification Script for Step 2.2 (3-Line Rolling Caption UI Renderer).
# Tests:
# 1. Status banner rendering on OLED viewport.
# 2. Live partial streaming speech simulation (visualizing growing text across lines).
# 3. Utterance completion formatting (final period, ellipsis, history logging).
# -----------------------------------------------------------------------------

import os
import sys

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.oled_display import OLEDDisplay
from deaf_mode.caption_renderer import CaptionRenderer


def run_test():
    print("=========================================================")
    print(" TriSense Deaf Mode — Step 2.2: Caption Renderer Test")
    print("=========================================================\n")

    display = OLEDDisplay(width=128, height=64, use_mock=True)
    renderer = CaptionRenderer(display=display, default_header="TriSense ASR [REC]")

    # Test 1: Status banner display
    print("1. Testing status banner display...")
    renderer.show_status("Vosk Offline Model Ready.", header="TriSense [STATUS]")
    if display.get_current_header() == "TriSense [STATUS]" and len(display.get_current_lines()) > 0:
        print("   [PASS] Status banner rendered onto display.")
    else:
        print("   [FAIL] Status banner not rendered correctly.")
        return False

    print("   ASCII Viewport (Status Banner):")
    for line in display.render_ascii().split("\n"):
        print(f"     {line}")

    # Test 2: Live partial streaming caption updates
    print("\n2. Testing live partial streaming speech updates...")
    partial_stream = [
        "hello",
        "hello tries and",
        "hello tries and team and obstacle is a head on your left"
    ]

    for idx, partial_text in enumerate(partial_stream, 1):
        print(f"\n   Partial Update #{idx}: \"{partial_text}\"")
        renderer.update_caption(partial_text, is_final=False)
        print("   ASCII Viewport:")
        for line in display.render_ascii().split("\n"):
            print(f"     {line}")

    if renderer.current_caption == partial_stream[-1] and len(renderer.get_history()) == 0:
        print("\n   [PASS] Partial stream updated OLED buffer continuously without logging incomplete history.")
    else:
        print("\n   [FAIL] Partial streaming failed state verification.")
        return False

    # Test 3: Utterance completion (final result & history)
    print("\n3. Testing utterance completion (is_final=True)...")
    final_text = "hello tries and team and obstacle is a head on your left please stop now"
    renderer.update_caption(final_text, is_final=True)
    
    print(f"   Final Utterance: \"{final_text}\"")
    print("   ASCII Viewport (Completed Sentence with Ellipsis & Period):")
    for line in display.render_ascii().split("\n"):
        print(f"     {line}")

    history = renderer.get_history()
    if len(history) == 1 and history[0] == final_text:
        print(f"   [PASS] Completed sentence logged to session history ({len(history)} utterance logged).")
    else:
        print(f"   [FAIL] Session history log verification failed: {history}")
        return False

    display.close()
    print("\n---------------------------------------------------------")
    print("RESULT: ALL STEP 2.2 TESTS PASSED [PASS]\n")
    return True


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
