from typing import Optional

import cv2
import numpy as np

from src.sources.base import FrameSource


class RtspSource(FrameSource):
    """A real CCTV/RTSP camera stream. This is the only source type that should ever be
    labeled as a genuinely live, non-demo camera in the backend. Untested against real
    hardware in this project (see README limitations) — the RTSP URL/credentials are
    supplied by the administrator via the Cameras page and never hardcoded."""

    is_live = True
    label = "rtsp"

    def __init__(self, rtsp_url: str) -> None:
        self.capture = cv2.VideoCapture(rtsp_url)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open RTSP stream: {rtsp_url}")

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self.capture.read()
        return frame if ok else None

    def release(self) -> None:
        self.capture.release()
