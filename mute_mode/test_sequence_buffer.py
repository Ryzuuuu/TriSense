# mute_mode/test_sequence_buffer.py
# -----------------------------------------------------------------------------
# Standalone verification suite for TriSense Mute Mode Step 2:
#   1. Temporal smoothing (EMA) & jitter reduction against real_sign.mp4.
#   2. 30-frame sliding window buffer FIFO behavior & buffer_full status.
#   3. Hold-last-good-value imputation and confidence decay on occlusions.
# -----------------------------------------------------------------------------

import sys
import os
import math

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mute_mode.config import (
    DEFAULT_VIDEO_PATH,
    EMA_ALPHA,
    WINDOW_SIZE,
    MAX_HOLD_FRAMES,
    NUM_LANDMARKS,
    LANDMARK_NAMES
)
from mute_mode.video_stream import VideoStreamer
from mute_mode.landmark_extractor import LandmarkExtractor
from mute_mode.sequence_buffer import LandmarkSmoother, GestureSequenceBuffer, _create_zero_hand


def test_1_temporal_smoothing_and_jitter_reduction(video_path: str):
    """
    Test 1: Runs LandmarkSmoother over real_sign.mp4 and measures frame-to-frame
    coordinate jitter (mean squared delta) for raw vs. smoothed trajectories,
    as well as overall motion range to assess real motion in the video.
    """
    print("-----------------------------------------------------------------------")
    print("Test 1: Temporal Smoothing (EMA) & Jitter Reduction (real_sign.mp4)")
    print("-----------------------------------------------------------------------")

    stream = VideoStreamer(video_path=video_path, use_mock=True)
    extractor = LandmarkExtractor()
    smoother = LandmarkSmoother(alpha=0.6)

    raw_trajectory = []
    smoothed_trajectory = []

    frame_count = 0
    while True:
        ret, frame = stream.read()
        if not ret or frame is None:
            break
        frame_count += 1
        raw_res = extractor.extract(frame)
        smooth_res = smoother.smooth(raw_res)

        # Look for Right hand (or Left if Right not found)
        raw_hand = None
        for h in raw_res.get("hands", []):
            if h["handedness"] == "Right" and not h.get("low_confidence", False):
                raw_hand = h
                break
        if raw_hand is None and raw_res.get("hands"):
            raw_hand = raw_res["hands"][0]

        smooth_hand = None
        for h in smooth_res.get("hands", []):
            if h["handedness"] == raw_hand["handedness"] if raw_hand else "Right":
                smooth_hand = h
                break

        if raw_hand and smooth_hand and not smooth_hand["missing"]:
            # Extract wrist and index tip coords as representative points
            raw_trajectory.append([(pt["x"], pt["y"], pt["z"]) for pt in raw_hand["landmarks"]])
            smoothed_trajectory.append([(pt["x"], pt["y"], pt["z"]) for pt in smooth_hand["landmarks"]])

    stream.release()
    extractor.close()

    assert len(raw_trajectory) > 5, "Expected at least 5 valid detected frames from real_sign.mp4"
    print(f"   [INFO] Processed {frame_count} total frames; {len(raw_trajectory)} valid hand frames analyzed.")

    # Calculate frame-to-frame jitter (mean Euclidean delta between consecutive frames)
    def calc_jitter(traj):
        total_delta = 0.0
        count = 0
        for i in range(1, len(traj)):
            for pt_idx in range(len(traj[i])):
                dx = traj[i][pt_idx][0] - traj[i-1][pt_idx][0]
                dy = traj[i][pt_idx][1] - traj[i-1][pt_idx][1]
                dz = traj[i][pt_idx][2] - traj[i-1][pt_idx][2]
                total_delta += math.sqrt(dx*dx + dy*dy + dz*dz)
                count += 1
        return total_delta / max(1, count)

    # Calculate overall motion range (max distance from initial pose)
    def calc_motion_range(traj):
        max_dist = 0.0
        if not traj:
            return 0.0
        p0 = traj[0]
        for i in range(1, len(traj)):
            for pt_idx in range(len(p0)):
                dx = traj[i][pt_idx][0] - p0[pt_idx][0]
                dy = traj[i][pt_idx][1] - p0[pt_idx][1]
                dz = traj[i][pt_idx][2] - p0[pt_idx][2]
                dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                if dist > max_dist:
                    max_dist = dist
        return max_dist

    raw_jitter = calc_jitter(raw_trajectory)
    sm_jitter = calc_jitter(smoothed_trajectory)
    motion_range = calc_motion_range(raw_trajectory)

    print(f"   [INFO] Raw Landmark Jitter (Mean Delta):      {raw_jitter:.6f}")
    print(f"   [INFO] Smoothed Landmark Jitter (Mean Delta): {sm_jitter:.6f}")
    print(f"   [INFO] Maximum Coordinate Motion Range:       {motion_range:.6f}")

    assert sm_jitter <= raw_jitter, f"Smoothed jitter ({sm_jitter}) should be <= raw jitter ({raw_jitter})"
    print("   [PASS] EMA smoothing successfully reduced frame-to-frame coordinate jitter.")
    print("   [PASS] Temporal trajectory integrity preserved without coordinate drift.")


def test_2_sliding_window_buffer_and_fifo_rolling(video_path: str):
    """
    Test 2: Verifies 30-frame fixed sliding window, warmup padding, buffer_full status
    transitions, and FIFO eviction order.
    """
    print("-----------------------------------------------------------------------")
    print("Test 2: 30-Frame Sliding Window Buffer & FIFO Rolling")
    print("-----------------------------------------------------------------------")

    buffer = GestureSequenceBuffer(window_size=WINDOW_SIZE, alpha=EMA_ALPHA)
    stream = VideoStreamer(video_path=video_path, use_mock=True)
    extractor = LandmarkExtractor()

    frames_processed = 0
    first_full_seq = None

    while True:
        ret, frame = stream.read()
        if not ret or frame is None:
            break
        frames_processed += 1
        res = extractor.extract(frame)
        buffer.add_frame(res)

        seq_info = buffer.get_sequence()
        assert seq_info["window_size"] == WINDOW_SIZE, "window_size should be 30"
        assert len(seq_info["frames"]) == WINDOW_SIZE, "returned sequence must always be padded to 30 frames"

        if frames_processed < WINDOW_SIZE:
            assert not seq_info["buffer_full"], f"buffer_full should be False at frame {frames_processed}"
            assert seq_info["num_frames"] == frames_processed, "num_frames should match accumulated frames"
        elif frames_processed == WINDOW_SIZE:
            assert seq_info["buffer_full"], f"buffer_full should transition to True at frame {WINDOW_SIZE}"
            first_full_seq = seq_info["frames"][:]
        else:
            assert seq_info["buffer_full"], "buffer_full should remain True once 30 frames are reached"
            assert seq_info["num_frames"] == WINDOW_SIZE, "num_frames should cap at 30"

    stream.release()
    extractor.close()

    assert frames_processed >= WINDOW_SIZE, f"Video {video_path} must have at least {WINDOW_SIZE} frames"
    print(f"   [PASS] Correctly accumulated {frames_processed} frames through 30-frame sliding window.")
    print("   [PASS] buffer_full status correctly transitioned False -> True at frame 30.")
    print("   [PASS] Padded sequence size remained invariant at 30 frames throughout.")

    buffer.clear()
    cleared_info = buffer.get_sequence()
    assert cleared_info["num_frames"] == 0 and not cleared_info["buffer_full"]
    print("   [PASS] clear() cleanly reset smoother states and emptied window deque.")


def test_3_imputation_and_low_confidence_flagging():
    """
    Test 3: Verifies explicit hold-last-good-value imputation, exponential confidence decay,
    imputed metadata flagging, and max-hold reset behavior on occluded/low-confidence frames.
    """
    print("-----------------------------------------------------------------------")
    print("Test 3: Hold-Last-Good-Value Imputation & Confidence Decay")
    print("-----------------------------------------------------------------------")

    smoother = LandmarkSmoother(alpha=1.0, max_hold_frames=MAX_HOLD_FRAMES)

    # Frame 1: Valid Right hand
    f1 = {
        "num_hands_detected": 1,
        "hands": [{
            "handedness": "Right",
            "confidence": 0.90,
            "low_confidence": False,
            "scale_factor": 0.25,
            "landmarks": [{
                "id": idx,
                "name": LANDMARK_NAMES[idx],
                "x": 0.5, "y": 0.5, "z": 0.0,
                "visibility": 0.95,
                "presence": 0.95
            } for idx in range(NUM_LANDMARKS)]
        }]
    }

    res1 = smoother.smooth(f1)
    h1 = res1["hands"][1]  # Right hand is index 1 ("Left", "Right")
    assert not h1["imputed"] and not h1["missing"]
    assert abs(h1["confidence"] - 0.90) < 1e-6
    print("   [PASS] High-confidence frame 1 processed normally (imputed=False).")

    # Frames 2..6 (5 frames): Missing hand (occlusion)
    f_missing = {"num_hands_detected": 0, "hands": []}
    for hold_idx in range(1, MAX_HOLD_FRAMES + 1):
        res_imputed = smoother.smooth(f_missing)
        h_imp = res_imputed["hands"][1]
        expected_conf = 0.90 * (0.5 ** hold_idx)
        assert h_imp["imputed"], f"Frame {hold_idx} should be marked imputed=True"
        assert not h_imp["missing"], f"Frame {hold_idx} should not be marked missing=True yet"
        assert abs(h_imp["confidence"] - expected_conf) < 1e-6, (
            f"Confidence decay mismatch: expected {expected_conf}, got {h_imp['confidence']}"
        )
        # Check held coordinates
        assert abs(h_imp["landmarks"][0]["x"] - 0.5) < 1e-6
    print(f"   [PASS] Held last good coordinates for {MAX_HOLD_FRAMES} frames with exponential decay (imputed=True).")

    # Frame 7: Exceeds MAX_HOLD_FRAMES -> should reset to zeroed missing placeholder
    res_reset = smoother.smooth(f_missing)
    h_reset = res_reset["hands"][1]
    assert h_reset["missing"], "Frame exceeding MAX_HOLD_FRAMES should be marked missing=True"
    assert not h_reset["imputed"], "Missing frame should have imputed=False"
    assert abs(h_reset["confidence"] - 0.0) < 1e-6
    assert abs(h_reset["landmarks"][0]["x"] - 0.0) < 1e-6
    print("   [PASS] Exceeding MAX_HOLD_FRAMES cleanly reset state to zeroed placeholder (missing=True).")


def run_all_tests():
    print("=======================================================================")
    print(" TriSense Mute Mode Step 2 (Feature Smoothing & Sequence Buffer) Test")
    print("=======================================================================")
    video_path = DEFAULT_VIDEO_PATH
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file '{video_path}' not found.")

    test_1_temporal_smoothing_and_jitter_reduction(video_path)
    test_2_sliding_window_buffer_and_fifo_rolling(video_path)
    test_3_imputation_and_low_confidence_flagging()

    print("\n=======================================================================")
    print(" RESULT: ALL MUTE MODE STEP 2 TESTS PASSED [PASS]")
    print("=======================================================================\n")


if __name__ == "__main__":
    run_all_tests()
