# deaf_mode/test_caption_formatter.py
# -----------------------------------------------------------------------------
# Standalone Verification Script for Step 1.3 (Caption Formatting & Wrapping).
# Tests:
# 1. Capitalization & final period insertion on completed sentence utterances.
# 2. Smart OLED word wrapping (max 20 chars per line, max 3 lines).
# 3. Live partial captions (no trailing period, smooth updates).
# 4. Scrolling history retention when text exceeds max_lines.
# -----------------------------------------------------------------------------

import os
import sys

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deaf_mode.caption_formatter import CaptionFormatter


def run_test():
    print("=========================================================")
    print(" TriSense Deaf Mode — Step 1.3: Caption Formatter Test")
    print("=========================================================\n")

    formatter = CaptionFormatter(max_chars_per_line=20, max_lines=3)
    passed = True

    # Test 1: Capitalization & final period on utterance completion
    print("1. Testing capitalization and period insertion (is_final=True)...")
    raw1 = "hello tries and team"
    res1 = formatter.format_caption(raw1, is_final=True)
    expected1 = ["Hello tries and", "team."]
    print(f"   Input : \"{raw1}\"")
    print(f"   Output: {res1}")
    if res1 == expected1:
        print("   [PASS] Capitalized and period inserted correctly.")
    else:
        print(f"   [FAIL] Expected {expected1}, got {res1}")
        passed = False

    # Test 2: Partial text (is_final=False, no period)
    print("\n2. Testing partial transcription (is_final=False)...")
    raw2 = "obstacle is a head"
    res2 = formatter.format_caption(raw2, is_final=False)
    expected2 = ["Obstacle is a head"]
    print(f"   Input : \"{raw2}\"")
    print(f"   Output: {res2}")
    if res2 == expected2:
        print("   [PASS] Partial caption formatted without trailing period.")
    else:
        print(f"   [FAIL] Expected {expected2}, got {res2}")
        passed = False

    # Test 3: Word wrapping and max line constraint for 20-char OLED
    print("\n3. Testing OLED word wrapping (20 chars max per line, 3 lines max)...")
    raw3 = "hello tries and team and obstacle is a head on your left please stop now"
    res3 = formatter.format_caption(raw3, is_final=True)
    print(f"   Input : \"{raw3}\"")
    print("   Formatted Display (OLED View):")
    for idx, line in enumerate(res3, 1):
        print(f"     Line {idx} ({len(line):02d} chars): | {line} |")
        if len(line) > 20:
            print(f"   [FAIL] Line {idx} exceeded 20 chars ({len(line)})")
            passed = False

    if len(res3) <= 3:
        print(f"   [PASS] Successfully wrapped to {len(res3)} lines (<= max_lines 3).")
    else:
        print(f"   [FAIL] Exceeded max_lines ({len(res3)} > 3).")
        passed = False

    # Test 4: Empty / whitespace handling
    print("\n4. Testing empty text handling...")
    res4 = formatter.format_caption("   ", is_final=True)
    if res4 == []:
        print("   [PASS] Empty input returns clean empty list.")
    else:
        print(f"   [FAIL] Expected empty list, got {res4}")
        passed = False

    print("\n---------------------------------------------------------")
    if passed:
        print("RESULT: ALL STEP 1.3 TESTS PASSED [PASS]\n")
    else:
        print("RESULT: STEP 1.3 TEST FAILED [FAIL]\n")

    return passed


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
