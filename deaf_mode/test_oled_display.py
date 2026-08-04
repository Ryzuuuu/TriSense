# deaf_mode/test_oled_display.py
# -----------------------------------------------------------------------------
# Standalone Verification Script for Step 2.1 (OLED Display Abstraction Layer).
# Tests:
# 1. OLEDDisplay initialization (auto-detect / mock mode) and screen clearing.
# 2. Subtitle text rendering with status header.
# 3. ASCII viewport formatting (for headless console visual inspection).
# 4. Dynamic frame updates and subtitle transitions.
# -----------------------------------------------------------------------------

import os
import sys

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.oled_display import OLEDDisplay


def run_test():
    print("=========================================================")
    print(" TriSense Deaf Mode — Step 2.1: OLED Display Test")
    print("=========================================================\n")

    print("1. Testing OLEDDisplay initialization and clear()...")
    display = OLEDDisplay(width=128, height=64, use_mock=True)
    print(f"   Mode: {display.mode}")
    display.clear()
    if display.get_current_header() == "" and display.get_current_lines() == []:
        print("   [PASS] Display buffer initialized and cleared.")
    else:
        print("   [FAIL] Display clear() did not reset buffer.")
        return False

    print("\n2. Testing subtitle text rendering with status header...")
    header = "TriSense ASR [REC]"
    test_lines = [
        "...and obstacle is a",
        "head on your left",
        "please stop now."
    ]
    display.display_text_lines(test_lines, header=header)
    
    if display.get_current_header() == header and display.get_current_lines() == test_lines:
        print("   [PASS] Header and subtitle lines loaded into OLED buffer correctly.")
    else:
        print("   [FAIL] OLED buffer contents do not match input lines.")
        return False

    print("\n3. Testing ASCII OLED Viewport Rendering...")
    ascii_box = display.render_ascii()
    print("   Rendered ASCII Viewport:")
    for line in ascii_box.split("\n"):
        print(f"     {line}")
        
    if "+--------------------+" in ascii_box and "TriSense ASR [REC]" in ascii_box and "head on your left" in ascii_box:
        print("   [PASS] ASCII viewport box rendered header and text correctly.")
    else:
        print("   [FAIL] ASCII viewport box missing expected border or text.")
        return False

    print("\n4. Testing dynamic subtitle transition (frame update)...")
    new_header = "TriSense ASR [REC]"
    new_lines = [
        "Path clear.",
        "Resume normal pace."
    ]
    display.display_text_lines(new_lines, header=new_header)
    if display.get_current_lines() == new_lines and len(display.get_current_lines()) == 2:
        print("   [PASS] Display cleanly transitioned to new 2-line subtitle frame.")
    else:
        print("   [FAIL] Display failed to update frame buffer.")
        return False

    display.close()
    print("\n---------------------------------------------------------")
    print("RESULT: ALL STEP 2.1 TESTS PASSED [PASS]\n")
    return True


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
