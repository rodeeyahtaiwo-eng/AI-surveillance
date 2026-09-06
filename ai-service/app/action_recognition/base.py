from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.schemas import DetectionResult


@dataclass
class ActionObservation:
    """Output of the action recognition stage. `metrics` carries the raw geometric
    signals (proximity, movement speed, person count) so the captioning and threat
    stages can use them without recomputing — see docs/ai-pipeline.md Stage 2.

    `mode="REAL"` means this observation was produced by genuine model inference — it
    is NOT a claim that the labeled event actually occurred, and it is NOT evidence the
    producing model is fully validated. See docs/ai-pipeline.md "Stage 2 — X3D-S
    refinement" for what mode=REAL does and doesn't mean for the X3D-S adapter
    specifically, and docs/phase2c-training.md through phase2g-controlled-retest.md for
    the (limited) validation evidence behind it."""

    label: str
    confidence: float
    mode: str  # "REAL" or "DEMO"
    metrics: Dict[str, float] = field(default_factory=dict)


class ActionRecognitionAdapter(ABC):
    """Stage 2 interface: consumes a *sequence* of (timestamp, detections) — not a
    single frame — and returns a recognized action. See docs/ai-pipeline.md Stage 2 for
    why this project's current default adapter is a geometric heuristic, not a trained
    model, and what a real one would need.

    `clip_frames` is optional and additive (Phase 2H): a short buffer of raw decoded
    frames for adapters that need actual pixels (e.g. X3D-S), not just detection boxes.
    Existing adapters that only reason over detections (e.g. the geometry heuristic)
    simply ignore it — this parameter changes nothing for them."""

    mode: str

    @abstractmethod
    def recognize(
        self,
        window: List[Tuple[datetime, List[DetectionResult]]],
        clip_frames: Optional[List[np.ndarray]] = None,
    ) -> ActionObservation:
        raise NotImplementedError
