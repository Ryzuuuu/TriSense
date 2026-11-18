# mute_mode/holistic.py
# -----------------------------------------------------------------------------
# Hands + upper body landmark extraction for TriSense Mute Mode (v2).
#
# The v1 extractor normalised every hand to its own wrist and scale, which
# throws away WHERE the hands are and HOW they move relative to the body. In
# ASL those two cues carry a large part of the meaning (MOTHER and FATHER share
# a handshape and differ only by location), so v2 also runs the MediaPipe Pose
# landmarker and keeps everything in raw image coordinates. Feature engineering
# happens later in mute_mode/features.py, identically for training and live use.
#
# Per frame we return:
#   pose : (33, 4)  x, y, z, visibility   (x is aspect corrected: x * W / H)
#   lh   : (21, 3)  left hand  x, y, z    (same coordinate frame as pose)
#   rh   : (21, 3)  right hand x, y, z
#   lh_ok, rh_ok : bool presence flags
#
# "Left" and "right" refer to the signer's own hands. They are assigned by
# matching each detected hand to the nearest pose wrist, which is more robust
# than MediaPipe's handedness label on non mirrored video.
# -----------------------------------------------------------------------------

import os
import urllib.request
from typing import Dict, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")
HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

# MediaPipe Pose indices for the signer's wrists
POSE_L_WRIST, POSE_R_WRIST = 15, 16


def _ensure_model(url: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, os.path.basename(url))
    if not os.path.exists(path):
        print(f"[HOLISTIC] Downloading {os.path.basename(url)} ...")
        urllib.request.urlretrieve(url, path)
    return path


def empty_frame() -> Dict[str, np.ndarray]:
    return {
        "pose": np.zeros((33, 4), np.float32),
        "lh": np.zeros((21, 3), np.float32),
        "rh": np.zeros((21, 3), np.float32),
        "lh_ok": False,
        "rh_ok": False,
        "pose_ok": False,
    }


class HolisticExtractor:
    """MediaPipe Tasks HandLandmarker + PoseLandmarker in VIDEO mode."""

    def __init__(self, num_hands: int = 2, min_conf: float = 0.4):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        self._mp = mp
        mode = vision.RunningMode.VIDEO
        self.hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_ensure_model(HAND_MODEL_URL)),
            running_mode=mode,
            num_hands=num_hands,
            min_hand_detection_confidence=min_conf,
            min_hand_presence_confidence=min_conf,
            min_tracking_confidence=min_conf,
        ))
        self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_ensure_model(POSE_MODEL_URL)),
            running_mode=mode,
            num_poses=1,
            min_pose_detection_confidence=0.4,
            min_pose_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        ))
        self._last_ts = -1
        # Pose and hands run in parallel: MediaPipe releases the GIL during inference,
        # so this cuts per frame latency from (pose + hands) to roughly max(pose, hands).
        from concurrent.futures import ThreadPoolExecutor
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pose")

    def extract(self, bgr_frame, timestamp_ms: Optional[int] = None) -> Dict[str, np.ndarray]:
        import cv2

        out = empty_frame()
        if bgr_frame is None:
            return out
        h, w = bgr_frame.shape[:2]
        ax = w / float(h)  # aspect correction so x and y share a unit
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

        ts = int(timestamp_ms) if timestamp_ms is not None else self._last_ts + 33
        if ts <= self._last_ts:  # VIDEO mode requires strictly increasing timestamps
            ts = self._last_ts + 1
        self._last_ts = ts

        pose_future = self._pool.submit(self.pose.detect_for_video, image, ts)
        hres = self.hands.detect_for_video(image, ts)
        pres = pose_future.result()
        if pres.pose_landmarks:
            lms = pres.pose_landmarks[0]
            out["pose"] = np.array(
                [[p.x * ax, p.y, p.z * ax, getattr(p, "visibility", 1.0) or 0.0] for p in lms], np.float32)
            out["pose_ok"] = True

        hands = []
        for i, lms in enumerate(hres.hand_landmarks or []):
            arr = np.array([[p.x * ax, p.y, p.z * ax] for p in lms], np.float32)
            label = None
            if hres.handedness and i < len(hres.handedness) and hres.handedness[i]:
                label = hres.handedness[i][0].category_name
            hands.append((arr, label))

        self._assign_hands(out, hands)
        return out

    @staticmethod
    def _assign_hands(out, hands):
        if not hands:
            return
        if out["pose_ok"]:
            lw = out["pose"][POSE_L_WRIST, :2]
            rw = out["pose"][POSE_R_WRIST, :2]
            if len(hands) == 1:
                arr = hands[0][0]
                side = "lh" if np.linalg.norm(arr[0, :2] - lw) < np.linalg.norm(arr[0, :2] - rw) else "rh"
                out[side], out[side + "_ok"] = arr, True
            else:
                a, b = hands[0][0], hands[1][0]
                cost_ab = np.linalg.norm(a[0, :2] - lw) + np.linalg.norm(b[0, :2] - rw)
                cost_ba = np.linalg.norm(b[0, :2] - lw) + np.linalg.norm(a[0, :2] - rw)
                left, right = (a, b) if cost_ab <= cost_ba else (b, a)
                out["lh"], out["lh_ok"] = left, True
                out["rh"], out["rh_ok"] = right, True
            return
        # No pose: fall back to MediaPipe's label. On a non mirrored camera image
        # MediaPipe's "Left" is the signer's right hand.
        for arr, label in hands[:2]:
            side = "rh" if label == "Left" else "lh"
            if not out[side + "_ok"]:
                out[side], out[side + "_ok"] = arr, True

    def close(self):
        if getattr(self, "_pool", None) is not None:
            self._pool.shutdown(wait=True)
        for m in (getattr(self, "hands", None), getattr(self, "pose", None)):
            if m is not None:
                m.close()


def stack_frames(frames) -> Dict[str, np.ndarray]:
    """List of per frame dicts -> dict of stacked arrays (T, ...)."""
    if not frames:
        frames = [empty_frame()]
    return {
        "pose": np.stack([f["pose"] for f in frames]).astype(np.float32),
        "lh": np.stack([f["lh"] for f in frames]).astype(np.float32),
        "rh": np.stack([f["rh"] for f in frames]).astype(np.float32),
        "lh_ok": np.array([f["lh_ok"] for f in frames], bool),
        "rh_ok": np.array([f["rh_ok"] for f in frames], bool),
        "pose_ok": np.array([f["pose_ok"] for f in frames], bool),
    }


def extract_video(path: str, frame_start: int = 1, frame_end: int = -1, max_frames: int = 400,
                  extractor: Optional[HolisticExtractor] = None) -> Optional[Dict[str, np.ndarray]]:
    """Runs the extractor over frames [frame_start, frame_end] (1 based, inclusive, -1 = last)."""
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not (5.0 <= fps <= 120.0):
        fps = 25.0
    own = extractor is None
    ex = extractor or HolisticExtractor()
    frames, idx = [], 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if idx < frame_start:
                continue
            if frame_end > 0 and idx > frame_end:
                break
            # keep inputs small, MediaPipe rescales internally anyway
            h, w = frame.shape[:2]
            if max(h, w) > 640:
                s = 640.0 / max(h, w)
                frame = cv2.resize(frame, (int(w * s), int(h * s)))
            frames.append(ex.extract(frame, int(len(frames) * 1000.0 / fps)))
            if len(frames) >= max_frames:
                break
    finally:
        cap.release()
        if own:
            ex.close()
    if len(frames) < 8:
        return None
    seq = stack_frames(frames)
    seq["fps"] = np.float32(fps)
    return seq
