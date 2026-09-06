from typing import List

import numpy as np

from app.detection.base import ObjectDetectionAdapter
from app.schemas import DetectionResult


class MockDetectionAdapter(ObjectDetectionAdapter):
    """Deterministic fake detector — no model, no torch/ultralytics dependency. Used for
    fast unit/integration tests (DETECTION_ADAPTER=mock) and as a fallback when no real
    model is available. Always clearly labeled mode="DEMO"."""

    mode = "DEMO"

    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        h, w = image.shape[:2]
        return [
            DetectionResult(
                object="person",
                confidence=0.88,
                bounding_box=[w * 0.1, h * 0.1, w * 0.4, h * 0.9],
                mode="DEMO",
            )
        ]
