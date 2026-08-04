# mute_mode/mock_video.py
# -----------------------------------------------------------------------------
# Video file streaming wrapper for TriSense Mute Mode software verification.
# Wraps a recorded test video file (e.g. real_sign.mp4) using OpenCV and streams
# real video pixel frames sequentially without synthetic pixel generation.
# -----------------------------------------------------------------------------

import os
try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


class MockVideoStream:
    """
    Streams real video frames sequentially from a recorded test video file on disk.
    Acts as the software-validation substitute for a live Pi webcam stream.
    
    Raises FileNotFoundError if the specified video file is not present on disk,
    enforcing that real recorded footage is used rather than synthetic stand-ins.
    """
    def __init__(self, video_path: str):
        self.video_path = video_path
        self._cap = None
        self._fps = 30.0
        self._frame_count = 0
        self._init_stream()

    def _init_stream(self):
        if not _HAS_CV2:
            raise ImportError(
                "OpenCV (cv2) is required for MockVideoStream to read video files, "
                "but it is not installed in the current environment."
            )

        if not os.path.exists(self.video_path):
            raise FileNotFoundError(
                f"Real test video file not found at '{self.video_path}'.\n"
                "As requested in Option A, please record or place a real video clip "
                "(e.g., a short ASL gesture recording) at this path before running Mute Mode tests."
            )

        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            raise RuntimeError(f"OpenCV failed to open video file at '{self.video_path}'.")

        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        print(f"[MOCK_VIDEO] Opened real video stream '{self.video_path}' ({self._fps:.1f} FPS, ~{self._frame_count} frames).")

    def read(self):
        """
        Reads and returns the next frame from the recorded video.
        Returns (True, frame) if a frame was read, or (False, None) at EOF.
        """
        if not self._cap or not self._cap.isOpened():
            return False, None
        
        ret, frame = self._cap.read()
        return ret, frame

    def reset(self):
        """Rewinds the video stream to the first frame."""
        if self._cap and self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def release(self):
        """Releases the underlying OpenCV video capture handle."""
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[MOCK_VIDEO] Video stream released.")

    def is_opened(self) -> bool:
        return bool(self._cap and self._cap.isOpened())

    def get_fps(self) -> float:
        return self._fps
