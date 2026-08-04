# mute_mode/landmark_extractor.py
# -----------------------------------------------------------------------------
# TriSense Mute Mode Step 1: Landmark Extraction Pipeline.
# Uses MediaPipe Hands to extract 21 3D keypoints per hand per frame.
# Normalizes keypoints precisely relative to wrist position and hand bounding scale.
# Exposes per-landmark confidence and visibility scores; explicitly flags
# low-confidence detections without silently dropping or fabricating coordinates.
#
# Fails loudly if MediaPipe is unavailable or DLL loading fails.
# -----------------------------------------------------------------------------

import math
from typing import Dict, Any, List, Optional
from mute_mode.config import (
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    CONFIDENCE_FLAG_THRESHOLD,
    NUM_LANDMARKS,
    LANDMARK_NAMES,
    WRIST
)

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    import mediapipe as mp
    _HAS_MEDIAPIPE = True
except (ImportError, AttributeError, OSError) as e:
    _HAS_MEDIAPIPE = False
    _MEDIAPIPE_ERROR = str(e)


class LandmarkExtractor:
    """
    Extracts 21 3D hand landmarks per detected hand from video frames using MediaPipe Hands.
    Performs precise wrist-relative translation and bounding-scale normalization.
    """
    def __init__(
        self,
        max_num_hands: int = MAX_NUM_HANDS,
        min_detection_confidence: float = MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = MIN_TRACKING_CONFIDENCE
    ):
        if not _HAS_MEDIAPIPE:
            raise RuntimeError(
                f"MediaPipe is required for Mute Mode landmark extraction but could not be loaded: "
                f"{_MEDIAPIPE_ERROR if '_MEDIAPIPE_ERROR' in globals() else 'ImportError'}."
            )
        if not _HAS_CV2:
            raise RuntimeError("OpenCV (cv2) is required for color conversion in LandmarkExtractor.")

        self.max_num_hands = max_num_hands
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence

        self._mp_hands = mp.solutions.hands
        try:
            self.hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=self.max_num_hands,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MediaPipe Hands: {e}")
        print("[LANDMARK_EXTRACTOR] Initialized MediaPipe Hands (21 3D keypoints per hand).")

    def extract(self, bgr_frame: Any) -> Dict[str, Any]:
        """
        Processes a BGR video frame and extracts normalized 3D hand landmarks.
        
        Returns a dictionary:
        {
            "num_hands_detected": int,
            "hands": [
                {
                    "handedness": str,            # "Left" or "Right"
                    "confidence": float,          # Hand detection classification score
                    "low_confidence": bool,       # True if confidence < threshold
                    "scale_factor": float,        # Bounding scale used for normalization
                    "landmarks": [
                        {
                            "id": int,
                            "name": str,
                            "x": float,           # Normalized x relative to wrist
                            "y": float,           # Normalized y relative to wrist
                            "z": float,           # Normalized z relative to wrist
                            "visibility": float,
                            "presence": float,
                            "low_confidence": bool # True if landmark visibility/confidence is low
                        },
                        ... # 21 landmarks total
                    ]
                },
                ...
            ]
        }
        """
        if bgr_frame is None:
            return {"num_hands_detected": 0, "hands": []}

        # Convert frame to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)

        if not results.multi_hand_landmarks:
            return {"num_hands_detected": 0, "hands": []}

        hands_list: List[Dict[str, Any]] = []

        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # Extract handedness and classification score
            handedness_str = "Unknown"
            hand_conf = 0.0
            if results.multi_handedness and hand_idx < len(results.multi_handedness):
                cls = results.multi_handedness[hand_idx].classification[0]
                handedness_str = cls.label
                hand_conf = float(cls.score)

            hand_low_conf = (hand_conf < CONFIDENCE_FLAG_THRESHOLD)

            # Step 1: Extract raw coordinates and metadata for all 21 keypoints
            raw_pts = []
            for idx, lm in enumerate(hand_landmarks.landmark):
                vis = getattr(lm, "visibility", 1.0)
                pres = getattr(lm, "presence", 1.0)
                raw_pts.append({
                    "id": idx,
                    "name": LANDMARK_NAMES[idx],
                    "raw_x": float(lm.x),
                    "raw_y": float(lm.y),
                    "raw_z": float(lm.z),
                    "visibility": float(vis),
                    "presence": float(pres)
                })

            # Step 2: Translate coordinates relative to wrist (index 0)
            wrist_x = raw_pts[WRIST]["raw_x"]
            wrist_y = raw_pts[WRIST]["raw_y"]
            wrist_z = raw_pts[WRIST]["raw_z"]

            trans_pts = []
            max_dist = 0.0
            for pt in raw_pts:
                tx = pt["raw_x"] - wrist_x
                ty = pt["raw_y"] - wrist_y
                tz = pt["raw_z"] - wrist_z
                dist = math.sqrt(tx * tx + ty * ty + tz * tz)
                if dist > max_dist:
                    max_dist = dist
                trans_pts.append({
                    "id": pt["id"],
                    "name": pt["name"],
                    "tx": tx,
                    "ty": ty,
                    "tz": tz,
                    "visibility": pt["visibility"],
                    "presence": pt["presence"]
                })

            # Step 3: Scale normalization (divide by max distance from wrist to ensure scale invariance)
            scale = max_dist if max_dist >= 1e-6 else 1.0

            normalized_landmarks = []
            for pt in trans_pts:
                norm_x = pt["tx"] / scale
                norm_y = pt["ty"] / scale
                norm_z = pt["tz"] / scale

                lm_low_conf = (hand_low_conf or pt["visibility"] < CONFIDENCE_FLAG_THRESHOLD)

                normalized_landmarks.append({
                    "id": pt["id"],
                    "name": pt["name"],
                    "x": norm_x,
                    "y": norm_y,
                    "z": norm_z,
                    "visibility": pt["visibility"],
                    "presence": pt["presence"],
                    "low_confidence": lm_low_conf
                })

            hands_list.append({
                "handedness": handedness_str,
                "confidence": hand_conf,
                "low_confidence": hand_low_conf,
                "scale_factor": scale,
                "landmarks": normalized_landmarks
            })

        return {
            "num_hands_detected": len(hands_list),
            "hands": hands_list
        }

    def close(self):
        """Releases the MediaPipe Hands resources."""
        if hasattr(self, "hands") and self.hands:
            self.hands.close()
        print("[LANDMARK_EXTRACTOR] Closed MediaPipe Hands extractor.")
