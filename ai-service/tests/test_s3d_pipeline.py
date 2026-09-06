"""Tests for the S3D orchestration/gating logic in app/services/pipeline.py (Phase 2R)
-- mirrors tests/test_x3d_pipeline.py's structure exactly. Uses injected fake adapters
via monkeypatch; never loads real S3D weights. The central property under test: S3D's
output is SUPPLEMENTARY and must never influence threat_score."""

import numpy as np

from app.action_recognition.base import ActionObservation
from app.config import settings
from app.services import pipeline


def make_frame():
    return np.zeros((4, 4, 3), dtype=np.uint8)


def fill_clip_buffer(camera_id: str, n: int = 16) -> None:
    buf = pipeline.clip_buffer_store.get(camera_id)
    for _ in range(n):
        buf.add(make_frame())


class RecordingS3DAdapter:
    def __init__(self, observation: ActionObservation):
        self._observation = observation
        self.call_count = 0

    def recognize(self, window, clip_frames=None):
        self.call_count += 1
        return self._observation


class RaisingS3DAdapter:
    def recognize(self, window, clip_frames=None):
        raise RuntimeError("simulated S3D inference failure")


def kinetics_observation(label: str = "kinetics:fighting_candidate", confidence: float = 0.9) -> ActionObservation:
    # Deliberately uses an adversarial label that LOOKS threat-relevant, to prove the
    # "kinetics:" boundary (and pipeline separation) holds even in the worst case.
    return ActionObservation(
        label=label,
        confidence=confidence,
        mode="REAL",
        metrics={"s3d_top5": [{"label": label.replace("kinetics:", ""), "score": confidence}], "s3d_component": "s3d_kinetics400"},
    )


# --- default-off regression ----------------------------------------------------------


def test_s3d_adapter_disabled_by_default():
    assert settings.s3d_adapter == "none"
    assert pipeline.get_s3d_adapter() is None


def test_maybe_run_s3d_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(pipeline, "get_s3d_adapter", lambda: None)
    assert pipeline.maybe_run_s3d("cam-disabled") is None


# --- CameraWindow cooldown -------------------------------------------------------------


def test_should_evaluate_s3d_true_before_first_evaluation():
    window = pipeline.buffer_store.get("cam-s3d-fresh")
    assert window.should_evaluate_s3d(20) is True


def test_should_evaluate_s3d_false_immediately_after_marking():
    window = pipeline.buffer_store.get("cam-s3d-marked")
    window.mark_s3d_evaluated()
    assert window.should_evaluate_s3d(20) is False


def test_s3d_and_x3d_cooldowns_are_independent():
    # Two separate supplementary signals must not share rate-limit state.
    window = pipeline.buffer_store.get("cam-independent-cooldowns")
    window.mark_s3d_evaluated()
    assert window.should_evaluate_s3d(20) is False
    assert window.should_evaluate_x3d(20) is True


# --- maybe_run_s3d(): gating -----------------------------------------------------------


def test_insufficient_buffered_frames_skips_s3d(monkeypatch):
    fake = RecordingS3DAdapter(kinetics_observation())
    monkeypatch.setattr(pipeline, "get_s3d_adapter", lambda: fake)
    # Deliberately do NOT fill the clip buffer for this camera.

    result = pipeline.maybe_run_s3d("cam-s3d-no-frames")

    assert result is None
    assert fake.call_count == 0


def test_cooldown_prevents_repeated_s3d_calls(monkeypatch):
    fake = RecordingS3DAdapter(kinetics_observation())
    monkeypatch.setattr(pipeline, "get_s3d_adapter", lambda: fake)
    fill_clip_buffer("cam-s3d-cooldown-repeat")

    first = pipeline.maybe_run_s3d("cam-s3d-cooldown-repeat")
    second = pipeline.maybe_run_s3d("cam-s3d-cooldown-repeat")

    assert first is not None
    assert second is None  # rate-limited
    assert fake.call_count == 1


def test_s3d_exception_returns_none_and_still_marks_cooldown(monkeypatch):
    monkeypatch.setattr(pipeline, "get_s3d_adapter", lambda: RaisingS3DAdapter())
    fill_clip_buffer("cam-s3d-raises")

    result = pipeline.maybe_run_s3d("cam-s3d-raises")

    assert result is None
    window = pipeline.buffer_store.get("cam-s3d-raises")
    assert window.should_evaluate_s3d(settings.s3d_eval_cooldown_seconds) is False


# --- the critical semantic rule: S3D never influences threat_score --------------------


def test_s3d_prediction_never_reaches_the_threat_engine(monkeypatch):
    """Even with S3D enabled and returning an adversarial, threat-vocabulary-looking
    label, the score computed by evaluate_window() must be identical to what the
    geometry heuristic alone would have produced -- proving S3D's result is surfaced,
    never scored."""
    camera_id = "cam-s3d-isolation"
    fake = RecordingS3DAdapter(kinetics_observation(label="kinetics:fighting_candidate", confidence=0.99))
    monkeypatch.setattr(pipeline, "get_s3d_adapter", lambda: fake)
    fill_clip_buffer(camera_id)

    from datetime import datetime, timezone
    from app.schemas import DetectionResult

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    # The geometry heuristic reads one stationary person -> "standing" -> 0.05, exactly
    # as it would with S3D disabled. S3D's 0.99-confidence "fighting_candidate"-looking
    # label must NOT have changed this.
    assert action_result.label == "standing"
    assert action_result.threat_score == 0.05
    assert fake.call_count == 1  # S3D did run...
    assert action_result.s3d_prediction is not None  # ...and its result IS surfaced...
    assert action_result.s3d_prediction["label"] == "kinetics:fighting_candidate"
    assert action_result.s3d_prediction["component"] == "s3d_kinetics400"
    # ...but never merged into the scored label or score.
    assert action_result.s3d_prediction["label"] != action_result.label


def test_s3d_prediction_is_none_when_disabled():
    camera_id = "cam-s3d-off"
    from datetime import datetime, timezone
    from app.schemas import DetectionResult

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.s3d_prediction is None
