from abc import ABC, abstractmethod
from typing import List

import numpy as np

from app.schemas import DetectionResult


class ObjectDetectionAdapter(ABC):
    """Stage 1 interface. Any concrete detector — pretrained, fine-tuned, or a stub —
    implements this. See docs/ai-pipeline.md Stage 1. Swapping models means writing one
    new adapter class and pointing DETECTION_ADAPTER at it in app/config.py — nothing
    else in the pipeline changes."""

    mode: str  # "REAL" or "DEMO" — see the honesty policy in docs/ai-pipeline.md

    @abstractmethod
    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        """image: an OpenCV-style BGR numpy array (H, W, 3)."""
        raise NotImplementedError
