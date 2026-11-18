# mute_mode/recognizer.py
# -----------------------------------------------------------------------------
# Live sign recogniser for Mute Mode v2.
#
# v1 classified a fixed 30 frame window and cleared it after every prediction,
# with no idea where a sign starts or ends. v2 segments the stream by hand
# activity: a sign starts when a hand appears and ends when the hands drop out
# of view (or after MAX_SIGN_S). The whole segment is then resampled to the
# same fixed length used in training, so a slow and a fast signer look alike
# to the classifier, exactly as in training.
# -----------------------------------------------------------------------------

import os
import time
from collections import deque
from typing import Callable, Dict, List, Optional

import numpy as np
import torch

from mute_mode.features import sequence_features, trim_to_activity
from mute_mode.holistic import HolisticExtractor, stack_frames

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CHECKPOINT = os.path.join(HERE, "checkpoints", "sign_v2.pth")

MIN_SIGN_S = 0.35         # ignore blips shorter than this
END_AFTER_IDLE_S = 0.32   # this long without hands closes a sign
START_AFTER = 2           # consecutive frames with a hand that open a sign
# Thresholds are in seconds and converted with the measured frame rate, so the
# recogniser behaves the same at 25 fps on a laptop and ~8 fps on a Pi 4.
MAX_SIGN_S = 3.0          # force a decision on very long segments
CONF_THRESHOLD = 0.45


class LiveSignRecognizer:
    def __init__(self, checkpoint: str = DEFAULT_CHECKPOINT, conf_threshold: float = CONF_THRESHOLD,
                 on_prediction: Optional[Callable[[Dict], None]] = None, extractor=None, device: str = "cpu"):
        from mute_mode.classifier_v2 import load_v2

        self.model, self.vocabulary, self.meta = load_v2(checkpoint, device)
        self.extractor = extractor or HolisticExtractor()
        self.conf_threshold = conf_threshold
        self.on_prediction = on_prediction
        self._frames: List[dict] = []
        self._pre = deque(maxlen=4)       # a few frames before the trigger, so the onset is kept
        self._recording = False
        self._hand_run = 0
        self._idle_run = 0
        self._t0 = time.monotonic()
        self._fps_hist = deque(maxlen=30)
        self._last_ts = None
        self.last_landmarks = None  # most recent per frame landmark dict (for UIs)

    @property
    def fps(self) -> float:
        return float(np.median(self._fps_hist)) if self._fps_hist else 25.0

    def process_frame(self, bgr_frame, timestamp_s: Optional[float] = None) -> Optional[Dict]:
        """Feed one camera frame. Returns a prediction dict when a sign has just ended."""
        ts = time.monotonic() - self._t0 if timestamp_s is None else timestamp_s
        if self._last_ts is not None and ts > self._last_ts:
            self._fps_hist.append(1.0 / (ts - self._last_ts))
        self._last_ts = ts

        f = self.extractor.extract(bgr_frame, int(ts * 1000))
        self.last_landmarks = f
        has_hand = bool(f["lh_ok"] or f["rh_ok"])

        if not self._recording:
            self._pre.append(f)
            self._hand_run = self._hand_run + 1 if has_hand else 0
            if self._hand_run >= START_AFTER:
                self._recording = True
                self._frames = list(self._pre)
                self._idle_run = 0
            return None

        self._frames.append(f)
        self._idle_run = 0 if has_hand else self._idle_run + 1
        fps = self.fps
        too_long = len(self._frames) >= MAX_SIGN_S * fps
        if self._idle_run >= max(2, round(END_AFTER_IDLE_S * fps)) or too_long:
            frames = self._frames[:-self._idle_run] if self._idle_run else self._frames
            self._reset()
            if len(frames) >= max(4, round(MIN_SIGN_S * fps)):
                return self.classify_frames(frames)
        return None

    def classify_frames(self, frames: List[dict]) -> Dict:
        seq = trim_to_activity(stack_frames(frames))
        x = torch.from_numpy(sequence_features(seq)).unsqueeze(0)
        pred = self.model.predict_step(x, self.vocabulary, top_k=3)
        pred["accepted"] = pred["confidence"] >= self.conf_threshold
        pred["frames"] = len(frames)
        if self.on_prediction:
            self.on_prediction(pred)
        return pred

    @property
    def recording(self) -> bool:
        """True while a sign is being captured."""
        return self._recording

    def _reset(self):
        self._recording = False
        self._frames = []
        self._pre.clear()
        self._hand_run = 0
        self._idle_run = 0

    def close(self):
        self.extractor.close()
