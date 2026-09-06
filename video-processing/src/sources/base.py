from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class FrameSource(ABC):
    """A camera source: webcam, an uploaded/demo video file, or a real RTSP stream. See
    docs/demo.md — callers must know which kind they're using and label accordingly;
    this class does not itself lie about its nature (see `is_live` / `label`)."""

    is_live: bool  # True only for a genuinely live device/RTSP feed
    label: str

    @abstractmethod
    def read(self) -> Optional[np.ndarray]:
        """Returns the next frame (BGR numpy array), or None when the source is
        exhausted/unavailable."""
        raise NotImplementedError

    def release(self) -> None:
        pass
