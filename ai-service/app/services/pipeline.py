from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np

from app.action_recognition.base import ActionObservation, ActionRecognitionAdapter
from app.action_recognition.demo_heuristic import DemoHeuristicActionRecognizer
from app.captioning.base import CaptioningAdapter
from app.captioning.template_adapter import TemplateCaptioner
from app.common.clip_buffer import ClipBufferStore
from app.common.frame_buffer import FrameBufferStore
from app.common.logger import get_logger
from app.config import settings
from app.detection.base import ObjectDetectionAdapter
from app.detection.mock_adapter import MockDetectionAdapter
from app.schemas import ActionResult, DetectionResult
from app.temporal_prediction.base import TemporalPredictionAdapter
from app.threat.base import ThreatAssessmentAdapter
from app.threat.rule_based import CAPTION_KEYWORD_FLOOR, RuleBasedThreatEngine, contains_weapon_keyword

logger = get_logger(__name__)

# One process-wide rolling buffer per camera — see app/common/frame_buffer.py.
buffer_store = FrameBufferStore()

# Raw-pixel buffer for X3D-S (Phase 2H) — see app/common/clip_buffer.py. Populated in
# main.py alongside buffer_store regardless of whether X3D_ADAPTER is enabled (the cost
# of appending to a capped deque is trivial); only actually read if it's enabled.
clip_buffer_store = ClipBufferStore(settings.clip_buffer_max_frames)

# A geometry-heuristic reading this "elevated" is the only thing that gates an X3D-S
# call — see evaluate_window() below. Kept as a module-level constant, not config, since
# it's tied directly to demo_heuristic.py's label vocabulary, not something meant to be
# tuned independently.
X3D_GATING_LABELS = {"close_contact", "fighting_candidate"}

_detection_adapter: Optional[ObjectDetectionAdapter] = None
_action_adapter: Optional[ActionRecognitionAdapter] = None
_x3d_adapter: Optional[ActionRecognitionAdapter] = None
_x3d_adapter_failed = False  # sticky — see get_x3d_adapter()
_s3d_adapter: Optional[ActionRecognitionAdapter] = None
_s3d_adapter_failed = False  # sticky — see get_s3d_adapter(), mirrors _x3d_adapter_failed
_caption_adapter: Optional[CaptioningAdapter] = None
_threat_adapter: Optional[ThreatAssessmentAdapter] = None
_temporal_predictor: Optional[TemporalPredictionAdapter] = None


def get_detection_adapter() -> ObjectDetectionAdapter:
    """Lazily constructed singleton so importing this module never triggers a model
    load (useful for tests / DETECTION_ADAPTER=mock) — only the first real request does."""
    global _detection_adapter
    if _detection_adapter is None:
        if settings.detection_adapter == "yolov8":
            from app.detection.yolov8_adapter import YoloV8Adapter

            _detection_adapter = YoloV8Adapter()
        else:
            _detection_adapter = MockDetectionAdapter()
    return _detection_adapter


def get_action_adapter() -> ActionRecognitionAdapter:
    global _action_adapter
    if _action_adapter is None:
        _action_adapter = DemoHeuristicActionRecognizer()
    return _action_adapter


def get_x3d_adapter() -> Optional[ActionRecognitionAdapter]:
    """Lazily constructed singleton, mirroring get_weapon_adapter() — but unlike every
    other adapter factory in this file, this one can legitimately return None: X3D-S is
    optional and secondary (see app/action_recognition/x3d_violence_adapter.py), so a
    load failure here must never prevent the primary heuristic pipeline from working.
    `_x3d_adapter_failed` is sticky for the process lifetime — a failed load logs once
    and disables X3D-S rather than re-attempting (and re-failing) on every window."""
    global _x3d_adapter, _x3d_adapter_failed
    if settings.x3d_adapter != "x3d_violence":
        return None
    if _x3d_adapter_failed:
        return None
    if _x3d_adapter is None:
        try:
            from app.action_recognition.x3d_violence_adapter import X3DViolenceAdapter

            _x3d_adapter = X3DViolenceAdapter()
        except Exception as exc:  # noqa: BLE001 — any failure here must degrade, not crash
            logger.warning(
                f"X3D-S adapter failed to load — disabling for this run, falling back "
                f"to heuristic-only action recognition: {exc}"
            )
            _x3d_adapter_failed = True
            return None
    return _x3d_adapter


def get_s3d_adapter() -> Optional[ActionRecognitionAdapter]:
    """Lazily constructed singleton, mirroring get_x3d_adapter() exactly — S3D is
    optional and SUPPLEMENTARY (see app/action_recognition/s3d_kinetics_adapter.py), so
    a load failure here must never prevent the primary heuristic pipeline from working.
    `_s3d_adapter_failed` is sticky for the process lifetime, same reasoning as X3D-S's
    own flag: a failed load logs once and disables S3D rather than re-attempting (and
    re-failing) on every window."""
    global _s3d_adapter, _s3d_adapter_failed
    if settings.s3d_adapter != "s3d_kinetics400":
        return None
    if _s3d_adapter_failed:
        return None
    if _s3d_adapter is None:
        try:
            from app.action_recognition.s3d_kinetics_adapter import S3DKineticsAdapter

            _s3d_adapter = S3DKineticsAdapter()
        except Exception as exc:  # noqa: BLE001 — any failure here must degrade, not crash
            logger.warning(
                f"S3D Kinetics-400 adapter failed to load — disabling for this run: {exc}"
            )
            _s3d_adapter_failed = True
            return None
    return _s3d_adapter


def get_caption_adapter() -> CaptioningAdapter:
    global _caption_adapter
    if _caption_adapter is None:
        if settings.caption_adapter == "blip":
            from app.captioning.blip_adapter import BlipCaptioner

            _caption_adapter = BlipCaptioner()
        else:
            _caption_adapter = TemplateCaptioner()
    return _caption_adapter


def get_threat_adapter() -> ThreatAssessmentAdapter:
    global _threat_adapter
    if _threat_adapter is None:
        _threat_adapter = RuleBasedThreatEngine()
    return _threat_adapter


def get_temporal_predictor() -> Optional[TemporalPredictionAdapter]:
    """Lazily constructed singleton. Unlike the model-backed adapters above, this has
    no load-failure mode worth guarding (pure Python, no weights, no I/O) — but stays
    optional and None-returning for the same reason every other supplementary signal
    here is: TEMPORAL_PREDICTION_ADAPTER=none (default) must cost nothing and change
    nothing about existing behavior."""
    global _temporal_predictor
    if settings.temporal_prediction_adapter != "markov_v1":
        return None
    if _temporal_predictor is None:
        from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor

        _temporal_predictor = MarkovTemporalPredictor(max_history=settings.temporal_prediction_max_history)
    return _temporal_predictor


def detect_frame(image: np.ndarray) -> List[DetectionResult]:
    return get_detection_adapter().detect(image)


def maybe_refine_with_x3d(camera_id: str, observation: ActionObservation) -> ActionObservation:
    """Phase 2H: if the heuristic's reading for this window is already "elevated"
    (X3D_GATING_LABELS) and X3D-S is enabled, available, cooled down, and has enough
    buffered frames, run it and — ONLY if it corroborates (predicts Violence at or
    above x3d_confidence_threshold) — upgrade this observation's mode to REAL and its
    confidence to X3D-S's, WITHOUT changing the label.

    This function can only ever raise the confidence/honesty of an alert the heuristic
    already decided to raise, never invent one from a calm reading, and never suppress
    one X3D-S disagrees with — see the module docstring on X3DViolenceAdapter for why.
    Any failure (adapter unavailable, insufficient frames, inference exception) returns
    `observation` completely unchanged — this must never be the reason a window fails
    to evaluate.
    """
    if observation.label not in X3D_GATING_LABELS:
        return observation

    adapter = get_x3d_adapter()
    if adapter is None:
        return observation

    window = buffer_store.get(camera_id)
    if not window.should_evaluate_x3d(settings.x3d_eval_cooldown_seconds):
        return observation

    clip = clip_buffer_store.get(camera_id)
    if not clip.is_full_enough(15):  # x3d_violence_adapter.NUM_FRAMES (13) + margin
        return observation

    try:
        x3d_observation = adapter.recognize([], clip_frames=clip.snapshot())
    except Exception as exc:  # noqa: BLE001 — a bad clip must never break the window eval
        logger.warning(f"X3D-S inference failed for camera_id={camera_id}, using heuristic result: {exc}")
        return observation
    finally:
        window.mark_x3d_evaluated()  # cooldown applies whether it succeeded or not

    prob_violence = x3d_observation.metrics.get("x3d_prob_violence", 0.0)
    if x3d_observation.label != "fighting_candidate" or prob_violence < settings.x3d_confidence_threshold:
        logger.debug(
            f"X3D-S did not corroborate for camera_id={camera_id} "
            f"(P(violence)={prob_violence:.3f}) — keeping heuristic result as-is"
        )
        return observation

    logger.info(
        f"X3D-S corroborated '{observation.label}' for camera_id={camera_id} "
        f"(P(violence)={prob_violence:.3f}) — upgrading mode DEMO->REAL"
    )
    return ActionObservation(
        label=observation.label,  # preserved exactly, never overwritten by X3D-S
        confidence=prob_violence,
        mode="REAL",
        metrics={**observation.metrics, **x3d_observation.metrics},
    )


def maybe_run_s3d(camera_id: str) -> Optional[dict]:
    """Phase 2R — SUPPLEMENTARY ONLY. Runs S3D Kinetics-400 over the buffered clip, if
    enabled/available/cooled-down/sufficiently-buffered, and returns its raw prediction
    as a plain dict. This result is NEVER merged into the ActionObservation the threat
    engine scores, and NEVER influences threat_score — see
    app/action_recognition/s3d_kinetics_adapter.py's module docstring for why. Any
    failure (adapter unavailable, insufficient frames, inference exception) returns
    None — this must never be the reason a window fails to evaluate, exactly like
    maybe_refine_with_x3d()."""
    adapter = get_s3d_adapter()
    if adapter is None:
        return None

    window = buffer_store.get(camera_id)
    if not window.should_evaluate_s3d(settings.s3d_eval_cooldown_seconds):
        return None

    from app.action_recognition.s3d_kinetics_adapter import NUM_FRAMES

    clip = clip_buffer_store.get(camera_id)
    if not clip.is_full_enough(NUM_FRAMES):
        return None

    try:
        observation = adapter.recognize([], clip_frames=clip.snapshot())
    except Exception as exc:  # noqa: BLE001 — a bad clip must never break the window eval
        logger.warning(f"S3D inference failed for camera_id={camera_id}, skipping: {exc}")
        return None
    finally:
        window.mark_s3d_evaluated()  # cooldown applies whether it succeeded or not

    logger.info(
        f"S3D Kinetics-400 prediction for camera_id={camera_id}: {observation.label} "
        f"(confidence={observation.confidence:.3f}) — supplementary only, not threat-scored."
    )
    return {
        "label": observation.label,
        "confidence": observation.confidence,
        "top5": observation.metrics.get("s3d_top5"),
        "component": "s3d_kinetics400",
        "note": "Raw Kinetics-400 prediction, not mapped to any threat category.",
    }


def maybe_predict_temporal(camera_id: str, current_label: str, timestamp: datetime) -> Optional[dict]:
    """Phase 2R/2T — SUPPLEMENTARY ONLY. Predicts the next label from this camera's
    prior history (NOT including `current_label`, which is only recorded afterward —
    see TemporalPredictionAdapter.predict_next()'s docstring for why the order
    matters), then records `current_label` for future predictions AND resolves
    whatever was predicted at the LAST call for this camera against `current_label`
    (Phase 2T's "prediction -> outcome validation" — see PredictionOutcome). Never
    influences threat_score — RuleBasedThreatEngine.assess() never receives this
    value or the field is even computed before assess() runs (see evaluate_window())."""
    predictor = get_temporal_predictor()
    if predictor is None:
        return None

    predicted = predictor.predict_next(camera_id)
    outcome = predictor.observe(camera_id, current_label, timestamp)

    return {
        "predicted_label": predicted.predicted_label,
        "confidence": predicted.confidence,
        "based_on_label": predicted.based_on_label,
        "history_length": predicted.history_length,
        "source": predicted.source,
        "rationale": predicted.rationale,
        "distribution": predicted.distribution,
        # Phase 2T — outcome of the PREVIOUS prediction (made at the prior window's
        # evaluation), checked against `current_label` (what was actually just
        # observed). None if there was nothing pending to resolve.
        "previous_prediction_outcome": (
            {
                "predicted_label": outcome.predicted_label,
                "predicted_confidence": outcome.predicted_confidence,
                "actual_label": outcome.actual_label,
                "matched": outcome.matched,
            }
            if outcome is not None
            else None
        ),
    }


def evaluate_window(camera_id: str) -> Optional[Tuple[ActionResult, datetime, datetime]]:
    """Runs Stages 2-4 (action recognition -> captioning -> threat assessment) over the
    camera's current buffered window and marks it evaluated. None if the window is empty.

    Phase 2R adds two SUPPLEMENTARY, non-scoring signals — S3D (maybe_run_s3d) and the
    temporal predictor (maybe_predict_temporal) — surfaced on ActionResult but never
    passed to get_threat_adapter().assess(), which continues to see only the geometry
    heuristic's (optionally X3D-refined) `observation`, exactly as before this phase."""
    window = buffer_store.get(camera_id)
    entries = list(window.entries)
    if not entries:
        return None

    had_previous = window.last_evaluated_at is not None
    observation = get_action_adapter().recognize(entries)
    observation = maybe_refine_with_x3d(camera_id, observation)
    detections = window.all_detections()

    # Phase 2S — knife threat evidence: computes only the boolean persistence signal
    # here; app/threat/rule_based.py owns the actual scoring decision (see its
    # KNIFE_* constants). Uses count_recent_frames_with_object_as_of() measured relative
    # to the latest buffered frame's own timestamp rather than wall-clock "now" —
    # necessary because BLIP's synchronous, multi-second cost (when CAPTION_ADAPTER=blip)
    # otherwise pushes "now" far enough past earlier buffered frames' timestamps to make
    # a real, closely-spaced persistence pattern look falsely stale — see
    # app/common/frame_buffer.py's docstring and docs/phase2s-threat-reasoning.md for the
    # measured evidence.
    reference_time = window.window_end() or datetime.now(timezone.utc)
    knife_persisted = window.count_recent_frames_with_object_as_of(
        "knife", settings.knife_persistence_window_seconds, reference_time
    ) >= settings.knife_persistence_min_hits
    observation.metrics["knife_persisted"] = 1.0 if knife_persisted else 0.0

    clip = clip_buffer_store.get(camera_id)
    latest_frame = clip.snapshot()[-1] if clip.snapshot() else None
    description = get_caption_adapter().caption(detections, observation, frame=latest_frame, camera_id=camera_id)

    threat_score, rationale = get_threat_adapter().assess(
        observation, window.last_threat_score if had_previous else None
    )

    # Phase 2AC — narrow caption-based weapon-keyword corroboration fallback (see
    # app/threat/rule_based.py's CAPTION_WEAPON_KEYWORDS docstring for full reasoning).
    # Reads BLIP's raw caption text directly via get_last_result() — never the
    # formatted `description` string, so a real detector-grounded object name appended
    # in "Grounded detections: ..." is never double-counted as a caption-text match.
    # Applied strictly AFTER assess() returns, as a separate, clearly-logged floor —
    # never folded into RuleBasedThreatEngine's own scoring path, so this fallback
    # stays auditable and visibly distinct from real object-detection evidence.
    # get_last_result is a BlipCaptioner-specific extension, not part of the
    # CaptioningAdapter interface — getattr()'d defensively so this is a no-op for
    # TemplateCaptioner/mock adapters, which never produce free-text hallucination risk.
    get_last_result = getattr(get_caption_adapter(), "get_last_result", None)
    raw_caption_text = ""
    if callable(get_last_result):
        last_result = get_last_result(camera_id)
        if last_result:
            raw_caption_text = last_result.get("raw_caption") or ""
    matched_keyword = contains_weapon_keyword(raw_caption_text)
    person_present = observation.metrics.get("avg_person_count", 0.0) >= 0.5
    if matched_keyword and person_present and CAPTION_KEYWORD_FLOOR > threat_score:
        previous_threat_score = threat_score
        threat_score = CAPTION_KEYWORD_FLOOR
        rationale = (
            f"{rationale} [CAPTION-CORROBORATION (ungrounded, text-only signal, not a "
            f"verified detection): raw caption matched weapon/violence keyword "
            f"'{matched_keyword}' + person present -> raised from "
            f"{previous_threat_score:.2f} to {CAPTION_KEYWORD_FLOOR:.2f}]"
        )
        logger.warning(
            f"[caption-corroboration] camera_id={camera_id} matched_keyword="
            f"{matched_keyword!r} raw_caption={raw_caption_text!r} threat_score "
            f"{previous_threat_score:.2f} -> {CAPTION_KEYWORD_FLOOR:.2f}"
        )

    window_start, window_end = window.window_start(), window.window_end()
    window.mark_evaluated(threat_score)

    s3d_prediction = maybe_run_s3d(camera_id)
    temporal_prediction = maybe_predict_temporal(camera_id, observation.label, window_end)

    # Phase 2T — explainable output: append temporal PREDICTIVE CONTEXT to the
    # rationale, strictly AFTER threat_score/rationale were already finalized by
    # assess() above. This can only ever add explanatory text; it is structurally
    # incapable of changing threat_score, which was computed one step earlier from
    # `observation` alone. Phrased explicitly as a prediction ("model predicts"), never
    # as something that already happened — see docs/phase2t-temporal-reasoning.md
    # "P2 — Explainable output".
    if temporal_prediction and temporal_prediction.get("predicted_label"):
        rationale = (
            f"{rationale} Temporal context: current action is '{observation.label}'; "
            f"model predicts '{temporal_prediction['predicted_label']}' next "
            f"(confidence {temporal_prediction['confidence']:.2f}, based on "
            f"{temporal_prediction['history_length']} prior observations for this camera)."
        )

    action_result = ActionResult(
        label=observation.label,
        confidence=observation.confidence,
        description=description,
        mode=observation.mode,
        threat_score=threat_score,
        rationale=rationale,
        s3d_prediction=s3d_prediction,
        temporal_prediction=temporal_prediction,
    )
    assert window_start is not None and window_end is not None
    return action_result, window_start, window_end
