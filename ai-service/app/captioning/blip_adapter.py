"""BLIP image-captioning adapter (Phase 2R) — Salesforce/blip-image-captioning-base via
transformers. Real vision-language model inference, but its output is explicitly NOT
treated as ground truth. Read this before enabling CAPTION_ADAPTER=blip.

WHY THIS MATTERS (Phase 2Q evidence): running this exact model on a real local test
image, it produced "a woman in a white dress is standing in front of a mirror" — there
was no mirror anywhere in that image. A coherent caption is not a verified one. See
docs/phase2q-s3d-blip-temporal-feasibility.md and docs/phase2r-integration.md
"Grounding rules".

GROUNDING POLICY, enforced here:
1. Object names from the actual object detector (YOLO) are authoritative for
   what's "detected" — this adapter never creates, modifies, or touches a Detection.
   There is no code path anywhere in this class that constructs a DetectionResult; the
   raw BLIP caption is plain text, nothing more.
2. BLIP's raw caption is never fed back into anything that computes a threat score
   (RuleBasedThreatEngine.assess() takes an ActionObservation, never caption text —
   this is already structurally true of the whole pipeline, not a special case added
   here).
3. The final string this adapter returns keeps BLIP's raw sentence and the real,
   detector-confirmed object list visibly separate ("Grounded detections: ...") rather
   than blending them into one implicitly-verified sentence.
4. get_last_result() exposes the same raw_caption / grounded_objects / source split
   programmatically, for anything (tests, a future dashboard panel) that wants it
   without parsing the display string.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import cv2
import numpy as np

from app.action_recognition.base import ActionObservation
from app.captioning.base import CaptioningAdapter
from app.common.logger import get_logger
from app.config import settings
from app.schemas import DetectionResult

logger = get_logger(__name__)

MAX_NEW_TOKENS = 30
MODEL_NAME = "Salesforce/blip-image-captioning-base"


class BlipCaptioner(CaptioningAdapter):
    """mode="REAL": genuine BLIP inference occurred. This is NOT a claim that the
    caption is factually accurate — see module docstring. Callers must not treat the
    raw caption as a structured, verified detection."""

    mode = "REAL"

    def __init__(self, processor: Optional[object] = None, model: Optional[object] = None) -> None:
        # Injectable for tests (see tests/test_blip_captioner.py) — never touches the
        # network or the ~990MB checkpoint download, mirroring every other adapter's
        # `model=` injection pattern in this project.
        if processor is not None or model is not None:
            self._processor = processor
            self._model = model
        else:
            import torch  # noqa: F401
            from transformers import BlipForConditionalGeneration, BlipProcessor

            logger.info(f"Loading BLIP captioner ({MODEL_NAME})...")
            self._processor = BlipProcessor.from_pretrained(MODEL_NAME)
            self._model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME)
            self._model.eval()
            logger.info("BLIP captioner ready.")

        # Per-camera cooldown/cache state (Phase 2R) — this adapter owns its own
        # cadence gating rather than relying on CameraWindow, since CaptioningAdapter's
        # interface only ever receives camera_id, not the window object itself.
        self._last_result_by_camera: Dict[str, dict] = {}
        self._last_eval_at_by_camera: Dict[str, datetime] = {}

    def caption(
        self,
        detections: List[DetectionResult],
        action: ActionObservation,
        frame: Optional[np.ndarray] = None,
        camera_id: Optional[str] = None,
    ) -> str:
        grounded_objects = sorted({d.object for d in detections})
        now = datetime.now(timezone.utc)
        key = camera_id or "_default"

        cached = self._last_result_by_camera.get(key)
        on_cooldown = (
            key in self._last_eval_at_by_camera
            and (now - self._last_eval_at_by_camera[key]).total_seconds() < settings.caption_blip_cooldown_seconds
        )

        if frame is not None and not on_cooldown:
            try:
                raw_caption = self._generate(frame)
            except Exception as exc:  # noqa: BLE001 -- a caption failure must never break the window eval
                logger.warning(f"BLIP caption generation failed for camera_id={camera_id}: {exc}")
                raw_caption = cached["raw_caption"] if cached else "(caption unavailable)"
            else:
                self._last_eval_at_by_camera[key] = now
        elif cached is not None:
            # Reuse the most recent caption while on cooldown or with no frame
            # available, rather than regenerating or fabricating a new one.
            raw_caption = cached["raw_caption"]
        else:
            raw_caption = "(caption pending — insufficient data for this window)"

        result = {"raw_caption": raw_caption, "grounded_objects": grounded_objects, "source": "BLIP"}
        self._last_result_by_camera[key] = result

        grounded_text = (
            f" Grounded detections: {', '.join(grounded_objects)}."
            if grounded_objects
            else " Grounded detections: none."
        )
        return f"{raw_caption}{grounded_text}"

    def get_last_result(self, camera_id: Optional[str] = None) -> Optional[dict]:
        """Programmatic access to the last raw_caption/grounded_objects/source split
        for a camera, without parsing the display string — used by tests and available
        for any future UI that wants to render the distinction explicitly."""
        return self._last_result_by_camera.get(camera_id or "_default")

    def _generate(self, frame: np.ndarray) -> str:
        import torch
        from PIL import Image

        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        inputs = self._processor(images=image, return_tensors="pt")
        with torch.no_grad():
            out = self._model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
        return self._processor.decode(out[0], skip_special_tokens=True)
