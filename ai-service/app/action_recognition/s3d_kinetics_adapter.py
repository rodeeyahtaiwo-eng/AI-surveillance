"""S3D Kinetics-400 adapter (Phase 2R). SUPPLEMENTARY, not a replacement for
DemoHeuristicActionRecognizer: this adapter's output is never merged into the
ActionObservation the threat engine scores (see app/services/pipeline.py's
maybe_run_s3d()) — it is surfaced separately, as ActionResult.s3d_prediction, purely
for transparency.

READ THIS BEFORE ENABLING S3D_ADAPTER=s3d_kinetics400:

This is real torchvision inference on a genuine pretrained checkpoint
(S3D_Weights.KINETICS400_V1) — mode="REAL" means genuine model inference occurred, NOT
that a threat-relevant action was detected. Phase 2Q ran this exact model against a
real staged-aggressive test clip already in this project and found its top-5 predictions
were low-confidence (max 0.17) and entirely unrelated to aggression ("baby waking up",
"crying", "sneezing") — see docs/phase2q-s3d-blip-temporal-feasibility.md. Kinetics-400
itself has very few violence-specific classes to begin with.

This project does NOT map any Kinetics-400 label onto "fighting", "violence", or any
other threat category. The label returned is the model's own, unmodified, prefixed
`kinetics:` so it can never be confused with — or accidentally scored as — this
project's threat-relevant action vocabulary (standing/walking/close_contact/
fighting_candidate, see app/threat/rule_based.py). If the model
predicts something irrelevant to threat detection, it is returned exactly as
irrelevant — see docs/phase2r-integration.md "Critical semantic rule"."""

from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.action_recognition.base import ActionObservation, ActionRecognitionAdapter
from app.common.logger import get_logger
from app.schemas import DetectionResult

logger = get_logger(__name__)

NUM_FRAMES = 16


class S3DKineticsAdapter(ActionRecognitionAdapter):
    """See module docstring for the full honesty framing. Implements the same
    ActionRecognitionAdapter interface as DemoHeuristicActionRecognizer/
    X3DViolenceAdapter for consistency, but is called as a separate, parallel signal —
    never as a drop-in replacement — by app/services/pipeline.py."""

    mode = "REAL"

    def __init__(
        self,
        model: Optional[object] = None,
        categories: Optional[List[str]] = None,
        preprocess: Optional[object] = None,
    ) -> None:
        # Injectable for tests (see tests/test_s3d_kinetics_adapter.py) — mirrors
        # X3DViolenceAdapter's `model=` injection pattern. Passing a fake model never
        # touches torchvision's weight download or the filesystem.
        if model is not None:
            self._model = model
            self._categories = categories or []
            self._preprocess = preprocess
            return

        import torch  # noqa: F401 -- imported lazily, mirrors every other adapter here
        from torchvision.models.video import s3d, S3D_Weights

        logger.info("Loading S3D Kinetics-400 (torchvision, pretrained)...")
        weights = S3D_Weights.KINETICS400_V1
        self._model = s3d(weights=weights)
        self._model.eval()
        self._categories = list(weights.meta["categories"])
        self._preprocess = weights.transforms()
        logger.info("S3D Kinetics-400 adapter ready.")

    def recognize(
        self,
        window: List[Tuple[datetime, List[DetectionResult]]],
        clip_frames: Optional[List[np.ndarray]] = None,
    ) -> ActionObservation:
        """Reasons over `clip_frames` only — `window` (detection boxes) is unused,
        exactly like X3DViolenceAdapter. Raises ValueError if too few frames are
        buffered; callers (app/services/pipeline.py) are expected to check
        availability and catch failures themselves — this adapter never silently
        degrades, matching the existing X3D-S convention."""
        import torch

        if not clip_frames or len(clip_frames) < NUM_FRAMES:
            raise ValueError(
                f"S3DKineticsAdapter requires >= {NUM_FRAMES} buffered frames, "
                f"got {len(clip_frames) if clip_frames else 0}"
            )

        indices = np.linspace(0, len(clip_frames) - 1, NUM_FRAMES).astype(int)
        selected = [cv2.cvtColor(clip_frames[i], cv2.COLOR_BGR2RGB) for i in indices]
        clip = torch.from_numpy(np.stack(selected)).permute(0, 3, 1, 2)  # T,C,H,W
        batch = self._preprocess(clip).unsqueeze(0)  # official torchvision preprocessing

        with torch.no_grad():
            output = self._model(batch)

        probs = torch.nn.functional.softmax(output[0], dim=0)
        k = min(5, probs.shape[0])
        top_scores, top_idx = torch.topk(probs, k)
        top5 = [
            {"label": self._categories[int(i)] if self._categories else str(int(i)), "score": float(s)}
            for s, i in zip(top_scores, top_idx)
        ]
        top1 = top5[0]

        return ActionObservation(
            label=f"kinetics:{top1['label']}",
            confidence=top1["score"],
            mode="REAL",
            metrics={
                "s3d_top5": top5,
                "s3d_component": "s3d_kinetics400",
            },
        )
