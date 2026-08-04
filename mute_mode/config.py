# mute_mode/config.py
# -----------------------------------------------------------------------------
# Configuration and Constants for TriSense Mute Mode (Sign Language Pipeline).
# Defines MediaPipe Hands hyperparameters, landmark index mappings, and
# confidence thresholds for flagging low-confidence keypoints.
# -----------------------------------------------------------------------------

import os

# ── MediaPipe Hands Configuration ─────────────────────────────────────────────
MAX_NUM_HANDS = 2
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

# Threshold below which a detected hand or landmark is explicitly flagged as low confidence
CONFIDENCE_FLAG_THRESHOLD = 0.65

# ── Default Video Source Path ────────────────────────────────────────────────
DEFAULT_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "real_sign.mp4")

# ── 21 Hand Landmark Indices (MediaPipe Hands Standard Schema) ────────────────
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4

INDEX_FINGER_MCP = 5
INDEX_FINGER_PIP = 6
INDEX_FINGER_DIP = 7
INDEX_FINGER_TIP = 8

MIDDLE_FINGER_MCP = 9
MIDDLE_FINGER_PIP = 10
MIDDLE_FINGER_DIP = 11
MIDDLE_FINGER_TIP = 12

RING_FINGER_MCP = 13
RING_FINGER_PIP = 14
RING_FINGER_DIP = 15
RING_FINGER_TIP = 16

PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

NUM_LANDMARKS = 21

LANDMARK_NAMES = [
    "WRIST", "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
    "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP",
    "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP",
    "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP",
    "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP"
]

# ── Temporal Smoothing & Sequence Buffer Configuration (Step 2) ───────────────
EMA_ALPHA = 0.6               # Exponential moving average smoothing factor (0 < alpha <= 1)
WINDOW_SIZE = 30              # Sliding window buffer capacity (frames)
MAX_HOLD_FRAMES = 5           # Max consecutive frames to hold last good value during occlusion
