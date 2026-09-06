from typing import Optional

import cv2
import numpy as np

from src.sources.base import FrameSource


class FileSource(FrameSource):
    """Plays back an uploaded/local video file — NOT a live CCTV feed, regardless of
    what the file shows. Loops back to the start when it reaches the end, so a short
    demo clip can run indefinitely. Always tag cameras using this source as demo/isDemo
    in the backend — see docs/demo.md's rule that uploaded video is never presented as
    live."""

    is_live = False
    label = "file"

    def __init__(self, path: str, loop: bool = True) -> None:
        self.path = path
        self.loop = loop
        self.capture = cv2.VideoCapture(path)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open video file: {path}")

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self.capture.read()
        if not ok:
            if not self.loop:
                return None
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.capture.read()
            if not ok:
                return None
        return frame

    def release(self) -> None:
        self.capture.release()
