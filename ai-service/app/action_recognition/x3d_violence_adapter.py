"""Optional refinement adapter (Phase 2H) — real frozen X3D-S backbone + Phase 2C's
trained logistic-regression classifier head, over the pooled 2048-d features.

READ THIS BEFORE ENABLING X3D_ADAPTER=x3d_violence:

mode="REAL" on this adapter's output means the result came from genuine model
inference on the actual buffered frames — it does NOT mean violence was confirmed to
have occurred, and it does NOT mean this classifier has been independently validated
as reliable. The actual evidence, in full, lives in:
  docs/phase2c-training.md          — training on filtered RLVS; validation accuracy
                                       (99.6%/100% recall) is dominated by a still-
                                       partially-biased data stratum, flagged explicitly
                                       there as not to be trusted at face value.
  docs/phase2d-webcam-fix.md         — real webcam recording became possible.
  docs/phase2e-webcam-eval.md        — 8/8 real calm clips correctly read as
                                       NonViolence; proves the model doesn't misfire on
                                       ordinary footage, proves nothing about recall.
  docs/phase2f-staged-positive-test.md — 1 of 6 staged clips showed confirmed elevated
                                       motion; that one scored far above the calm range
                                       but never crossed the decision threshold.
  docs/phase2g-controlled-retest.md  — 2 of 3 clips showed confirmed elevated motion;
                                       one of them crossed the threshold (the first and
                                       only confirmed Violence prediction on this camera
                                       to date). Relationship between raw motion and
                                       P(Violence) is NOT monotonic across the n=3
                                       confirmed-elevated clips seen so far.

Net: real, motion-correlated signal on genuine deployment footage — not a validated
detector. This is exactly why this adapter is wired as a REFINEMENT that can only
corroborate an already-elevated heuristic reading, never independently trigger or
suppress an alert — see apply_x3d_refinement() in app/services/pipeline.py.

Preprocessing here intentionally duplicates scripts/x3d_common.py's math rather than
importing it: `scripts/` is training-side tooling only, never imported by `app/` (see
that module's own docstring). If either changes, the other must too — the Phase 2H
manual smoke test (scripts/smoke_test_live_x3d_adapter.py) checks the two paths still
agree on the same real clips.
"""

import json
import math
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.action_recognition.base import ActionObservation, ActionRecognitionAdapter
from app.common.logger import get_logger
from app.schemas import DetectionResult

logger = get_logger(__name__)

NUM_FRAMES = 13
CROP_SIZE = 182
MEAN = np.array([0.45, 0.45, 0.45])
STD = np.array([0.225, 0.225, 0.225])


def _preprocess_clip(frames: List[np.ndarray]):
    """Mirrors scripts/x3d_common.py's clip_tensor_from_video exactly, operating on
    already-decoded in-memory BGR frames (from the live clip buffer) instead of reading
    from a video file: uniform subsample to NUM_FRAMES, BGR->RGB, short-side scale to
    CROP_SIZE, center crop, stack, normalize, permute to (1, C, T, H, W)."""
    import torch

    if len(frames) < NUM_FRAMES:
        raise ValueError(f"X3D-S needs at least {NUM_FRAMES} frames, got {len(frames)}")

    indices = np.linspace(0, len(frames) - 1, NUM_FRAMES).astype(int)
    selected = [frames[i] for i in indices]

    processed = []
    for frame in selected:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        scale = CROP_SIZE / min(h, w)
        new_h, new_w = max(round(h * scale), CROP_SIZE), max(round(w * scale), CROP_SIZE)
        resized = cv2.resize(rgb, (new_w, new_h))
        top = (new_h - CROP_SIZE) // 2
        left = (new_w - CROP_SIZE) // 2
        processed.append(resized[top : top + CROP_SIZE, left : left + CROP_SIZE])

    clip = np.stack(processed, axis=0).astype(np.float32) / 255.0
    clip = (clip - MEAN) / STD
    clip = torch.from_numpy(clip).permute(3, 0, 1, 2).float()
    return clip.unsqueeze(0)


class _FeatureExtractor:
    """Duplicated from scripts/x3d_common.py's FeatureExtractor for the same
    app/-vs-scripts/ boundary reason as _preprocess_clip above — same forward-hook
    approach, verified in Phase 2C: model.blocks[5].pool outputs (1, 2048, 1, 2, 2),
    averaged over the residual spatial dims to a flat 2048-d feature vector."""

    def __init__(self, model) -> None:
        self.model = model
        self._captured = None
        model.blocks[5].pool.register_forward_hook(self._hook)

    def _hook(self, module, inp, out) -> None:
        self._captured = out

    def extract(self, clip_tensor) -> np.ndarray:
        import torch

        with torch.no_grad():
            self.model(clip_tensor)
        feat = self._captured.mean(dim=[2, 3, 4]).squeeze(0)
        return feat.numpy()


class X3DViolenceAdapter(ActionRecognitionAdapter):
    """See module docstring for the full honesty framing — read it before enabling
    this. mode="REAL" here means genuine inference, not a validated detector."""

    mode = "REAL"

    def __init__(
        self,
        extractor: Optional[object] = None,
        coef: Optional[np.ndarray] = None,
        intercept: Optional[float] = None,
    ) -> None:
        # Injectable for tests (see tests/test_x3d_violence_adapter.py) — passing a
        # fake extractor + coef/intercept never touches torch.hub, the network, or the
        # filesystem.
        if extractor is not None:
            self._extractor = extractor
            self._coef = coef
            self._intercept = intercept
            return

        import torch

        from app.config import settings

        logger.info("Loading X3D-S backbone (frozen) + trained violence classifier head...")
        model = torch.hub.load("facebookresearch/pytorchvideo", "x3d_s", pretrained=True)
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        self._extractor = _FeatureExtractor(model)

        with open(settings.x3d_head_path) as f:
            head = json.load(f)
        self._coef = np.array(head["coef"][0])
        self._intercept = float(head["intercept"][0])
        logger.info(f"X3D-S adapter ready ({head.get('note', 'no note in head file')}).")

    def recognize(
        self,
        window: List[Tuple[datetime, List[DetectionResult]]],
        clip_frames: Optional[List[np.ndarray]] = None,
    ) -> ActionObservation:
        """Reasons over `clip_frames` only — `window` (detection boxes) is unused by
        this adapter, unlike the geometry heuristic. Raises ValueError if clip_frames
        is missing or too short; callers (see pipeline.py) are expected to check
        availability before calling and to catch failures — this adapter does not
        silently degrade itself, the orchestration layer does."""
        if not clip_frames or len(clip_frames) < NUM_FRAMES:
            raise ValueError(
                f"X3DViolenceAdapter requires >= {NUM_FRAMES} buffered frames, "
                f"got {len(clip_frames) if clip_frames else 0}"
            )

        clip_tensor = _preprocess_clip(clip_frames)
        features = self._extractor.extract(clip_tensor)
        z = float(np.dot(features, self._coef) + self._intercept)
        prob_violence = 1.0 / (1.0 + math.exp(-z))

        if prob_violence >= 0.5:
            label, confidence = "fighting_candidate", prob_violence
        else:
            label, confidence = "no_activity", 1.0 - prob_violence

        return ActionObservation(
            label=label,
            confidence=confidence,
            mode="REAL",
            metrics={"x3d_prob_violence": prob_violence, "x3d_prob_nonviolence": 1.0 - prob_violence},
        )
