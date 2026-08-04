# mute_mode/video_stream.py
# -----------------------------------------------------------------------------
# Unified video stream abstraction for TriSense Mute Mode.
# Exposes a `.mode` property indicating whether frames are being read from a
# recorded test video file ("VideoFileStream") or a live physical camera
# ("HardwareCamera").
# -----------------------------------------------------------------------------

import os
from typing import Optional, Tuple
from mute_mode.mock_video import MockVideoStream
from mute_mode.config import DEFAULT_VIDEO_PATH

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


class VideoStreamer:
    """
    Unified video source for Mute Mode sign language recognition.
    
    Attributes:
        mode (str): "VideoFileStream" when reading from a recorded test video file,
                    or "HardwareCamera" when reading from a live physical camera device.
    """
    def __init__(self, video_path: Optional[str] = None, camera_index: int = 0, use_mock: bool = True):
        self._video_path = video_path or DEFAULT_VIDEO_PATH
        self._camera_index = camera_index
        self._use_mock = use_mock
        self._stream = None
        self._mode = "VideoFileStream" if use_mock else "HardwareCamera"
        self._init_stream()

    def _init_stream(self):
        if self._use_mock:
            self._mode = "VideoFileStream"
            self._stream = MockVideoStream(self._video_path)
        else:
            self._mode = "HardwareCamera"
            if not _HAS_CV2:
                raise ImportError("OpenCV (cv2) is required for HardwareCamera video streaming.")
            self._stream = cv2.VideoCapture(self._camera_index)
            if not self._stream.isOpened():
                raise RuntimeError(f"Failed to open hardware camera at device index {self._camera_index}.")
            print(f"[VIDEO_STREAM] Initialized HardwareCamera (device index {self._camera_index}).")

    @property
    def mode(self) -> str:
        """Returns 'VideoFileStream' or 'HardwareCamera'."""
        return self._mode

    def read(self) -> Tuple[bool, Optional[object]]:
        """
        Reads and returns the next frame.
        Returns:
            (ret, frame): ret is True if frame was successfully read, False otherwise.
        """
        if not self._stream:
            return False, None
        return self._stream.read()

    def release(self):
        """Releases the underlying video resource."""
        if self._stream:
            self._stream.release()
            self._stream = None
        print(f"[VIDEO_STREAM] Closed video stream ({self._mode}).")

    def is_opened(self) -> bool:
        if not self._stream:
            return False
        if hasattr(self._stream, "is_opened"):
            return self._stream.is_opened()
        return bool(self._stream.isOpened())
