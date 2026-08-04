# mute_mode/sequence_buffer.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode Step 2: Feature Smoothing & Gesture Sequence Buffer.
# 
# 1. LandmarkSmoother:
#    Applies Exponential Moving Average (EMA) temporal smoothing to normalized
#    hand landmark coordinates (x, y, z) to eliminate single-frame jitter without
#    lagging real sign language motion.
#
# 2. Imputation Strategy (Hold-Last-Good-Value with Confidence Decay):
#    When a detected hand is missing or marked low_confidence for up to
#    MAX_HOLD_FRAMES (5 frames, ~250ms), the smoother holds the last known valid
#    pose, explicitly tagging the frame with `imputed = True` and decaying its
#    confidence score exponentially (0.5^k). If missing beyond MAX_HOLD_FRAMES,
#    the state resets to an explicit zero-coordinate placeholder (`missing = True`).
#
# 3. GestureSequenceBuffer:
#    Fixed-length 30-frame sliding window (FIFO deque) that collects smoothed
#    landmark frames into a uniform temporal sample ready for downstream
#    sign language classification.
# -----------------------------------------------------------------------------

from collections import deque
from typing import Dict, Any, List, Optional
from mute_mode.config import (
    EMA_ALPHA,
    WINDOW_SIZE,
    MAX_HOLD_FRAMES,
    NUM_LANDMARKS,
    LANDMARK_NAMES,
    CONFIDENCE_FLAG_THRESHOLD
)


def _create_zero_hand(handedness: str) -> Dict[str, Any]:
    """Creates an explicit zero-coordinate placeholder hand pose for missing/reset frames."""
    landmarks = []
    for idx in range(NUM_LANDMARKS):
        landmarks.append({
            "id": idx,
            "name": LANDMARK_NAMES[idx],
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "visibility": 0.0,
            "presence": 0.0,
            "low_confidence": True
        })
    return {
        "handedness": handedness,
        "confidence": 0.0,
        "low_confidence": True,
        "imputed": False,
        "missing": True,
        "scale_factor": 1.0,
        "landmarks": landmarks
    }


class LandmarkSmoother:
    """
    Applies Exponential Moving Average (EMA) smoothing to 3D hand landmarks
    and manages occlusion/imputation using a hold-last-good-value strategy.
    """
    def __init__(
        self,
        alpha: float = EMA_ALPHA,
        max_hold_frames: int = MAX_HOLD_FRAMES
    ):
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"EMA alpha must be in (0.0, 1.0], got {alpha}")
        self.alpha = alpha
        self.max_hold_frames = max_hold_frames

        # Track previous smoothed pose per handedness ("Left", "Right")
        self._last_good_hand: Dict[str, Optional[Dict[str, Any]]] = {
            "Left": None,
            "Right": None
        }
        # Track consecutive missing/low-confidence frames per handedness
        self._hold_counts: Dict[str, int] = {
            "Left": 0,
            "Right": 0
        }

    def smooth(self, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes a raw frame result from LandmarkExtractor, applies EMA smoothing to valid
        hands, and handles occlusions/low-confidence frames via hold-last-good-value imputation.
        """
        raw_hands = extraction_result.get("hands", [])
        # Map raw hands by handedness
        detected_by_hand: Dict[str, Dict[str, Any]] = {}
        for h in raw_hands:
            h_name = h.get("handedness", "Unknown")
            if h_name in ("Left", "Right"):
                detected_by_hand[h_name] = h

        smoothed_hands: List[Dict[str, Any]] = []

        for h_name in ("Left", "Right"):
            raw_h = detected_by_hand.get(h_name)
            is_valid = raw_h is not None and not raw_h.get("low_confidence", False)

            if is_valid and raw_h is not None:
                # Valid high-confidence detection: apply EMA smoothing
                last_h = self._last_good_hand[h_name]
                new_lms = []
                for idx, pt in enumerate(raw_h["landmarks"]):
                    if last_h is not None and len(last_h["landmarks"]) > idx:
                        prev_pt = last_h["landmarks"][idx]
                        sm_x = self.alpha * pt["x"] + (1.0 - self.alpha) * prev_pt["x"]
                        sm_y = self.alpha * pt["y"] + (1.0 - self.alpha) * prev_pt["y"]
                        sm_z = self.alpha * pt["z"] + (1.0 - self.alpha) * prev_pt["z"]
                    else:
                        sm_x, sm_y, sm_z = pt["x"], pt["y"], pt["z"]

                    new_lms.append({
                        "id": pt["id"],
                        "name": pt["name"],
                        "x": sm_x,
                        "y": sm_y,
                        "z": sm_z,
                        "visibility": pt["visibility"],
                        "presence": pt["presence"],
                        "low_confidence": pt.get("low_confidence", False)
                    })

                smoothed_hand = {
                    "handedness": h_name,
                    "confidence": raw_h.get("confidence", 1.0),
                    "low_confidence": False,
                    "imputed": False,
                    "missing": False,
                    "scale_factor": raw_h.get("scale_factor", 1.0),
                    "landmarks": new_lms
                }
                self._last_good_hand[h_name] = smoothed_hand
                self._hold_counts[h_name] = 0
                smoothed_hands.append(smoothed_hand)

            else:
                # Missing or low-confidence hand -> apply hold-last-good-value strategy
                last_h = self._last_good_hand[h_name]
                if last_h is not None and self._hold_counts[h_name] < self.max_hold_frames:
                    self._hold_counts[h_name] += 1
                    decayed_conf = last_h["confidence"] * (0.5 ** self._hold_counts[h_name])
                    imputed_hand = {
                        "handedness": h_name,
                        "confidence": decayed_conf,
                        "low_confidence": (decayed_conf < CONFIDENCE_FLAG_THRESHOLD),
                        "imputed": True,
                        "missing": False,
                        "scale_factor": last_h["scale_factor"],
                        "landmarks": [dict(pt) for pt in last_h["landmarks"]]
                    }
                    smoothed_hands.append(imputed_hand)
                else:
                    # Exceeded max hold frames or no prior pose -> reset and produce missing placeholder
                    self._last_good_hand[h_name] = None
                    self._hold_counts[h_name] = 0
                    missing_hand = _create_zero_hand(h_name)
                    smoothed_hands.append(missing_hand)

        return {
            "num_hands_detected": len([h for h in smoothed_hands if not h["missing"]]),
            "hands": smoothed_hands
        }

    def reset(self):
        """Clears all smoother history and hold counts."""
        self._last_good_hand = {"Left": None, "Right": None}
        self._hold_counts = {"Left": 0, "Right": 0}


class GestureSequenceBuffer:
    """
    Fixed-length sliding window buffer (30 frames) that collects smoothed landmark
    frames into a temporal sequence ready for sign language classification.
    """
    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        alpha: float = EMA_ALPHA,
        max_hold_frames: int = MAX_HOLD_FRAMES
    ):
        if window_size <= 0:
            raise ValueError(f"window_size must be positive, got {window_size}")
        self.window_size = window_size
        self.buffer: deque = deque(maxlen=self.window_size)
        self.smoother = LandmarkSmoother(alpha=alpha, max_hold_frames=max_hold_frames)

    def add_frame(self, extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Smooths and imputes the incoming extraction frame using LandmarkSmoother,
        appends it to the rolling FIFO window, and returns the smoothed frame.
        """
        smoothed_frame = self.smoother.smooth(extraction_result)
        self.buffer.append(smoothed_frame)
        return smoothed_frame

    def get_sequence(self) -> Dict[str, Any]:
        """
        Returns the current 30-frame sequence tensor structure.
        If fewer than 30 frames are accumulated, pads the beginning with explicit
        zero-coordinate missing placeholder frames.
        """
        frames_list = list(self.buffer)
        num_accumulated = len(frames_list)
        buffer_full = (num_accumulated == self.window_size)

        if not buffer_full:
            pad_count = self.window_size - num_accumulated
            zero_frame = {
                "num_hands_detected": 0,
                "hands": [
                    _create_zero_hand("Left"),
                    _create_zero_hand("Right")
                ]
            }
            padded_frames = [zero_frame] * pad_count + frames_list
        else:
            padded_frames = frames_list

        return {
            "window_size": self.window_size,
            "num_frames": num_accumulated,
            "buffer_full": buffer_full,
            "frames": padded_frames
        }

    def clear(self):
        """Empties the sliding window buffer and resets the smoother."""
        self.buffer.clear()
        self.smoother.reset()
