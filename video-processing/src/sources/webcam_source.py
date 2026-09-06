from typing import Optional

import cv2
import numpy as np

from src.sources.base import FrameSource


class WebcamSource(FrameSource):
    """A genuinely live local webcam. This is real, not demo, footage — but it is still
    NOT a CCTV/RTSP feed, so the caller (run_camera.py) still tags cameras using it
    accordingly (see docs/demo.md)."""

    is_live = True
    label = "webcam"

    def __init__(self, device_index: int = 0) -> None:
        self.capture = cv2.VideoCapture(device_index)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open webcam device {device_index}")

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self.capture.read()
        return frame if ok else None

    def release(self) -> None:
        self.capture.release()
