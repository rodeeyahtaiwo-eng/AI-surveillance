"""Tests for the X3D-S orchestration/gating logic in app/services/pipeline.py — the
part that decides WHEN to call X3D-S and how to merge its result, not the adapter's own
math (see tests/test_x3d_violence_adapter.py for that). Uses injected fake adapters via
monkeypatch — never loads real X3D-S weights."""

import numpy as np
import pytest

from app.action_recognition.base import ActionObservation
from app.common.clip_buffer import CameraClipBuffer
from app.config import settings
from app.services import pipeline


def make_frame():
    return np.zeros((4, 4, 3), dtype=np.uint8)


def fill_clip_buffer(camera_id: str, n: int = 16) -> None:
    buf = pipeline.clip_buffer_store.get(camera_id)
    for _ in range(n):
        buf.add(make_frame())


class RecordingAdapter:
    """A fake ActionRecognitionAdapter that returns a canned observation and counts
    how many times it was actually invoked — used to prove gating/cooldown logic
    prevents calls, not just that the merge math is correct when it does run."""

    def __init__(self, observation: ActionObservation):
        self._observation = observation
        self.call_count = 0

    def recognize(self, window, clip_frames=None):
        self.call_count += 1
        return self._observation


class RaisingAdapter:
    def recognize(self, window, clip_frames=None):
        raise RuntimeError("simulated X3D-S inference failure")


def corroborating_observation(prob: float = 0.9) -> ActionObservation:
    return ActionObservation(
        label="fighting_candidate",
        confidence=prob,
        mode="REAL",
        metrics={"x3d_prob_violence": prob, "x3d_prob_nonviolence": 1 - prob},
    )


def disagreeing_observation(prob: float = 0.05) -> ActionObservation:
    return ActionObservation(
        label="no_activity",
        confidence=1 - prob,
        mode="REAL",
        metrics={"x3d_prob_violence": prob, "x3d_prob_nonviolence": 1 - prob},
    )


# --- CameraWindow cooldown (should_evaluate_x3d / mark_x3d_evaluated) --------------


def test_should_evaluate_x3d_true_before_first_evaluation():
    window = pipeline.buffer_store.get("cam-cooldown-fresh")
    assert window.should_evaluate_x3d(15) is True


def test_should_evaluate_x3d_false_immediately_after_marking():
    window = pipeline.buffer_store.get("cam-cooldown-marked")
    window.mark_x3d_evaluated()
    assert window.should_evaluate_x3d(15) is False


# --- get_x3d_adapter(): default-off regression -------------------------------------


def test_x3d_adapter_disabled_by_default():
    # conftest.py sets X3D_ADAPTER=none — this pins that the DEFAULT behavior (no env
    # override at all) is also "none", so a bare checkout with no .env is safe too.
    assert settings.x3d_adapter == "none"
    assert pipeline.get_x3d_adapter() is None


# --- maybe_refine_with_x3d(): gating ------------------------------------------------


def test_non_elevated_label_never_calls_x3d(monkeypatch):
    fake = RecordingAdapter(corroborating_observation())
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)

    original = ActionObservation(label="standing", confidence=0.6, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-non-elevated", original)

    assert result is original
    assert fake.call_count == 0


def test_disabled_adapter_leaves_observation_unchanged(monkeypatch):
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: None)

    original = ActionObservation(label="fighting_candidate", confidence=0.5, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-disabled", original)

    assert result is original


def test_insufficient_buffered_frames_skips_x3d(monkeypatch):
    fake = RecordingAdapter(corroborating_observation())
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)
    # Deliberately do NOT fill the clip buffer for this camera.

    original = ActionObservation(label="close_contact", confidence=0.5, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-no-frames", original)

    assert result is original
    assert fake.call_count == 0


def test_cooldown_prevents_repeated_x3d_calls(monkeypatch):
    fake = RecordingAdapter(corroborating_observation())
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)
    fill_clip_buffer("cam-cooldown-repeat")

    original = ActionObservation(label="fighting_candidate", confidence=0.5, mode="DEMO", metrics={})
    first = pipeline.maybe_refine_with_x3d("cam-cooldown-repeat", original)
    second = pipeline.maybe_refine_with_x3d("cam-cooldown-repeat", original)

    assert first.mode == "REAL"  # first call ran and corroborated
    assert second is original  # second call was rate-limited, not re-evaluated
    assert fake.call_count == 1


# --- maybe_refine_with_x3d(): merge behavior ---------------------------------------


def test_corroboration_upgrades_mode_and_confidence_but_preserves_label(monkeypatch):
    fake = RecordingAdapter(corroborating_observation(prob=0.87))
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)
    fill_clip_buffer("cam-corroborate")

    original = ActionObservation(
        label="fighting_candidate", confidence=0.55, mode="DEMO", metrics={"min_proximity_ratio": 0.1}
    )
    result = pipeline.maybe_refine_with_x3d("cam-corroborate", original)

    assert result.label == "fighting_candidate"  # unchanged — never overwritten
    assert result.mode == "REAL"
    assert result.confidence == 0.87
    assert result.metrics["min_proximity_ratio"] == 0.1  # original metrics preserved
    assert result.metrics["x3d_prob_violence"] == 0.87  # X3D's metrics merged in


def test_disagreement_leaves_original_observation_unchanged(monkeypatch):
    fake = RecordingAdapter(disagreeing_observation(prob=0.05))
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)
    fill_clip_buffer("cam-disagree")

    original = ActionObservation(label="close_contact", confidence=0.5, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-disagree", original)

    assert result is original
    assert result.mode == "DEMO"


def test_low_confidence_corroboration_below_threshold_is_not_applied(monkeypatch):
    # Predicts "fighting_candidate" but below x3d_confidence_threshold — must not upgrade.
    fake = RecordingAdapter(corroborating_observation(prob=settings.x3d_confidence_threshold - 0.01))
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: fake)
    fill_clip_buffer("cam-low-confidence")

    original = ActionObservation(label="fighting_candidate", confidence=0.5, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-low-confidence", original)

    assert result is original


def test_x3d_exception_falls_back_to_original_observation(monkeypatch):
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: RaisingAdapter())
    fill_clip_buffer("cam-raises")

    original = ActionObservation(label="fighting_candidate", confidence=0.5, mode="DEMO", metrics={})
    result = pipeline.maybe_refine_with_x3d("cam-raises", original)

    assert result is original  # must degrade cleanly, not propagate the exception


def test_x3d_exception_still_marks_cooldown(monkeypatch):
    # A failing model must not be retried on every single window either — the cooldown
    # applies whether the call succeeded or not (see the `finally` in maybe_refine_with_x3d).
    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: RaisingAdapter())
    fill_clip_buffer("cam-raises-cooldown")

    original = ActionObservation(label="fighting_candidate", confidence=0.5, mode="DEMO", metrics={})
    pipeline.maybe_refine_with_x3d("cam-raises-cooldown", original)

    window = pipeline.buffer_store.get("cam-raises-cooldown")
    assert window.should_evaluate_x3d(settings.x3d_eval_cooldown_seconds) is False
