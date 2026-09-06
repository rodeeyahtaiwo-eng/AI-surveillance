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

import re
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

import cv2
import numpy as np

from app.action_recognition.base import ActionObservation
from app.captioning.base import CaptioningAdapter
from app.captioning.template_adapter import build_structured_sentence
from app.common.logger import get_logger
from app.config import settings
from app.schemas import DetectionResult

logger = get_logger(__name__)

MAX_NEW_TOKENS = 30
MODEL_NAME = "Salesforce/blip-image-captioning-base"

# Phase 2AB — degenerate-repetition guard for generate(). Measured real failure mode:
# greedy decoding (the default, no repetition control at all before this phase) looped
# on a single token ("a woman is taking a selfie self self self self self..."). Two
# standard, minimal generation-level controls fix this at the source — not three, and
# not a threshold change: `no_repeat_ngram_size` forbids repeating any 3-word sequence
# (so a genuine short repeated phrase is still allowed once, just not looped forever),
# `repetition_penalty` discourages (does not forbid) reusing already-generated tokens,
# which is what breaks the single-token loop specifically. MAX_NEW_TOKENS (existing,
# unchanged) already bounds worst-case length.
NO_REPEAT_NGRAM_SIZE = 3
REPETITION_PENALTY = 1.3

# Defensive post-processing safety net (Part 6: "only if necessary") — collapses a run
# of the SAME word repeated 3+ times in a row (never legitimate English) down to one
# occurrence. Deliberately >=3, not >=2, so a genuine short repeat ("very very nice")
# is never touched -- only unambiguous degenerate loops are.
_DEGENERATE_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b){2,}", re.IGNORECASE)


def _collapse_degenerate_repetition(text: str) -> str:
    return _DEGENERATE_REPEAT_RE.sub(r"\1", text)


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
        # Phase 2AB — which cameras currently have a real _generate() call running in a
        # background thread, so caption() never blocks the calling thread (previously
        # ~1.8-2.2s measured on this CPU) and never kicks off a second overlapping
        # generation for the same camera while one is already in flight.
        self._generation_in_progress: Dict[str, bool] = {}
        self._generation_lock = threading.Lock()
        self._generation_threads: Dict[str, threading.Thread] = {}

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

        on_cooldown = (
            key in self._last_eval_at_by_camera
            and (now - self._last_eval_at_by_camera[key]).total_seconds() < settings.caption_blip_cooldown_seconds
        )

        # Phase 2AB: NEVER block the calling thread on real BLIP generation (measured
        # ~1.8-2.2s on this CPU) — this call used to be synchronous here, which meant a
        # slow caption delayed the whole evaluate_window() call, including the already-
        # finalized threat_score/action label reaching the backend. generate() now
        # always runs in a background thread; this method always returns immediately
        # with whatever is already cached (or the existing "pending" placeholder on a
        # cold camera), exactly like the on-cooldown path already did before this phase.
        if frame is not None and not on_cooldown:
            with self._generation_lock:
                already_running = self._generation_in_progress.get(key, False)
                if not already_running:
                    self._generation_in_progress[key] = True
                    self._last_eval_at_by_camera[key] = now  # starts the cooldown NOW, not when it finishes
                    thread = threading.Thread(target=self._generate_and_cache, args=(frame, key), daemon=True)
                    self._generation_threads[key] = thread
                    thread.start()

        # Read the cache AFTER the possible dispatch above (not before) and under the
        # same lock _generate_and_cache() writes under — otherwise a fast background
        # generation (or a real one that happens to finish between this line and the
        # dispatch) could be immediately clobbered by a stale value read before it ran.
        with self._generation_lock:
            cached = self._last_result_by_camera.get(key)
            raw_caption = cached["raw_caption"] if cached else "(caption pending — insufficient data for this window)"
            self._last_result_by_camera[key] = {"raw_caption": raw_caption, "grounded_objects": grounded_objects, "source": "BLIP"}

        # Phase 2AB — structured, activity-centric sentence (real detections + real
        # action label, no model call) is now the PRIMARY text; BLIP's own text (fresh
        # or cached, per the cooldown above) is demoted to a clearly-labeled
        # supplementary clause. See app/captioning/template_adapter.py's
        # build_structured_sentence() and this module's own docstring "GROUNDING
        # POLICY" — BLIP still never creates/modifies a Detection and is still never
        # read by the threat engine; this only changes which text is primary.
        structured = build_structured_sentence(detections, action, include_object_list=False)
        grounded_text = (
            f"Grounded detections: {', '.join(grounded_objects)}."
            if grounded_objects
            else "Grounded detections: none."
        )
        return f"{structured} {grounded_text} Visual context: {raw_caption}"

    def _generate_and_cache(self, frame: np.ndarray, key: str) -> None:
        """Runs the real, slow _generate() call off the calling thread and updates this
        camera's cache when done — the NEXT caption() call for this camera (whenever it
        happens) picks up the fresh text; the CURRENT call that triggered this already
        returned immediately with the previous value. Failure here is logged and
        swallowed, exactly matching the prior synchronous behavior's own error handling
        (a caption failure must never break anything downstream)."""
        try:
            raw_caption = self._generate(frame)
        except Exception as exc:  # noqa: BLE001 -- a caption failure must never break the window eval
            logger.warning(f"BLIP caption generation failed for camera_id={key}: {exc}")
        else:
            with self._generation_lock:
                existing = self._last_result_by_camera.get(key, {})
                self._last_result_by_camera[key] = {**existing, "raw_caption": raw_caption, "source": "BLIP"}
        finally:
            with self._generation_lock:
                self._generation_in_progress[key] = False

    def wait_for_pending_generation(self, camera_id: Optional[str] = None, timeout: float = 5.0) -> None:
        """Test/diagnostic helper only — production code never calls this (the whole
        point of Phase 2AB is that nothing needs to wait). Blocks until this camera's
        in-flight background generation (if any) finishes, so a test can assert on the
        freshly-generated text deterministically instead of racing a background thread."""
        thread = self._generation_threads.get(camera_id or "_default")
        if thread is not None:
            thread.join(timeout=timeout)

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
            out = self._model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE,
                repetition_penalty=REPETITION_PENALTY,
            )
        text = self._processor.decode(out[0], skip_special_tokens=True)
        return _collapse_degenerate_repetition(text)
