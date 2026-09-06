from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np

from app.action_recognition.base import ActionObservation
from app.schemas import DetectionResult


class CaptioningAdapter(ABC):
    """Stage 3 interface: turns detections + a recognized action into a natural-language
    description. See docs/ai-pipeline.md Stage 3. Two adapters exist: TemplateCaptioner
    (deterministic, no model) and, since Phase 2R, BlipCaptioner (real
    Salesforce/blip-image-captioning-base) — see app/captioning/blip_adapter.py for its
    grounding policy before trusting its output.

    `frame` and `camera_id` are optional and additive (Phase 2R), mirroring how
    ActionRecognitionAdapter.recognize()'s `clip_frames` parameter was added in Phase
    2H: TemplateCaptioner ignores both (it only ever reasons over detections + the
    action label, same as before). BlipCaptioner needs `frame` (raw pixels — it has no
    other source of pixels) and `camera_id` (for its own per-camera cooldown/cache,
    since it must not run every window — see CAPTION_BLIP_COOLDOWN_SECONDS)."""

    mode: str

    @abstractmethod
    def caption(
        self,
        detections: List[DetectionResult],
        action: ActionObservation,
        frame: Optional[np.ndarray] = None,
        camera_id: Optional[str] = None,
    ) -> str:
        raise NotImplementedError
