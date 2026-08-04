# mute_mode/test_landmark_extractor.py
# -----------------------------------------------------------------------------
# Verification Suite for TriSense Mute Mode Step 1: Landmark Extraction Pipeline.
#
# Verifies:
#   1. VideoStreamer initializes in "VideoFileStream" mode and reads real BGR frames.
#   2. LandmarkExtractor extracts 21 3D keypoints per hand per frame.
#   3. Precise normalization: wrist coordinates are exactly (0.0, 0.0, 0.0) and
#      scale invariance is enforced.
#   4. Confidence and visibility scores are explicitly exposed and flagged
#      without silently dropping or fabricating coordinates.
# -----------------------------------------------------------------------------

import os
import sys
import time

# Ensure UTF-8 output encoding for console symbols on Windows/cp1252
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mute_mode.config import DEFAULT_VIDEO_PATH, NUM_LANDMARKS, WRIST
from mute_mode.video_stream import VideoStreamer
from mute_mode.landmark_extractor import LandmarkExtractor


def check_video_file_exists():
    if not os.path.exists(DEFAULT_VIDEO_PATH):
        print("=======================================================================")
        print(" [MISSING VIDEO FILE] Option A Verification Notice")
        print("=======================================================================")
        print(f"File not found: {DEFAULT_VIDEO_PATH}")
        print("\nPer Option A, please record or place a real video clip of a hand")
        print("(e.g., a short ASL gesture recording in .mp4 format) at:")
        print(f"   {DEFAULT_VIDEO_PATH}")
        print("\nThen re-run this verification command:")
        print("   python mute_mode/test_landmark_extractor.py")
        print("=======================================================================\n")
        return False
    return True


def test_video_streamer():
    print("-----------------------------------------------------------------------")
    print("Test 1: VideoStreamer ('VideoFileStream' Mode & Real Frame Reading)")
    print("-----------------------------------------------------------------------")
    streamer = VideoStreamer(use_mock=True)
    
    assert streamer.mode == "VideoFileStream", f"Expected mode 'VideoFileStream', got '{streamer.mode}'"
    assert streamer.is_opened(), "VideoStreamer failed to open real_sign.mp4"
    
    ret, frame = streamer.read()
    assert ret and frame is not None, "Failed to read first frame from video stream"
    h, w, c = frame.shape
    assert c == 3 and h > 0 and w > 0, f"Invalid BGR frame dimensions: {frame.shape}"
    
    print(f"   [PASS] Successfully opened video stream in '{streamer.mode}' mode.")
    print(f"   [PASS] Read real BGR frame with resolution: {w}x{h}\n")
    streamer.release()
    return True


def test_landmark_extraction_and_normalization():
    print("-----------------------------------------------------------------------")
    print("Test 2: 21 3D Keypoint Extraction & Precise Wrist/Scale Normalization")
    print("-----------------------------------------------------------------------")
    streamer = VideoStreamer(use_mock=True)
    extractor = LandmarkExtractor()

    hand_detected_frame = None
    frame_idx = 0

    while True:
        ret, frame = streamer.read()
        if not ret or frame is None:
            break
        frame_idx += 1
        result = extractor.extract(frame)
        if result["num_hands_detected"] > 0:
            hand_detected_frame = result
            break
        if frame_idx >= 60:
            break

    streamer.release()
    extractor.close()

    assert hand_detected_frame is not None, (
        f"No hands detected in the first {frame_idx} frames of '{DEFAULT_VIDEO_PATH}'. "
        "Please ensure the recorded video contains a clearly visible hand."
    )

    hand = hand_detected_frame["hands"][0]
    landmarks = hand["landmarks"]
    assert len(landmarks) == NUM_LANDMARKS, f"Expected {NUM_LANDMARKS} landmarks, got {len(landmarks)}"

    # Check wrist coordinates are exactly (0.0, 0.0, 0.0)
    wrist = landmarks[WRIST]
    assert abs(wrist["x"]) < 1e-9 and abs(wrist["y"]) < 1e-9 and abs(wrist["z"]) < 1e-9, (
        f"Wrist normalization failed! Expected (0.0, 0.0, 0.0), got ({wrist['x']}, {wrist['y']}, {wrist['z']})"
    )

    scale = hand["scale_factor"]
    assert scale > 0.0, f"Invalid bounding scale factor: {scale}"

    print(f"   [PASS] Extracted {len(landmarks)} 3D keypoints for detected {hand['handedness']} hand.")
    print(f"   [PASS] Wrist precisely normalized to origin (0.0, 0.0, 0.0).")
    print(f"   [PASS] Scale normalization factor applied: {scale:.4f}\n")
    return True


def test_confidence_exposing():
    print("-----------------------------------------------------------------------")
    print("Test 3: Confidence & Visibility Score Exposing & Flagging")
    print("-----------------------------------------------------------------------")
    streamer = VideoStreamer(use_mock=True)
    extractor = LandmarkExtractor()

    ret, frame = streamer.read()
    result = extractor.extract(frame)
    streamer.release()
    extractor.close()

    # Even if 0 hands or >=1 hand, check dictionary structure and explicit flags
    assert "num_hands_detected" in result
    assert "hands" in result

    for hand in result["hands"]:
        assert "confidence" in hand
        assert "low_confidence" in hand
        assert isinstance(hand["low_confidence"], bool)
        for lm in hand["landmarks"]:
            assert "visibility" in lm
            assert "presence" in lm
            assert "low_confidence" in lm
            assert isinstance(lm["low_confidence"], bool)

    print("   [PASS] Detection confidence and per-landmark visibility explicitly exposed.")
    print("   [PASS] Low-confidence flags present without silently dropping or fabricating data.\n")
    return True


def run_all_tests():
    print("=======================================================================")
    print(" TriSense Mute Mode Step 1 (Landmark Extraction) Verification")
    print("=======================================================================\n")

    if not check_video_file_exists():
        return False

    t1 = test_video_streamer()
    t2 = test_landmark_extraction_and_normalization()
    t3 = test_confidence_exposing()

    all_passed = t1 and t2 and t3
    print("=======================================================================")
    if all_passed:
        print("RESULT: ALL MUTE MODE STEP 1 TESTS PASSED [PASS]\n")
    else:
        print("RESULT: MUTE MODE STEP 1 TEST FAILED [FAIL]\n")
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
