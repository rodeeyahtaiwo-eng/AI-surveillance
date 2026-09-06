"""Tests for the temporal-predictor orchestration in app/services/pipeline.py (Phase
2R). Uses the real MarkovTemporalPredictor (pure Python, no model) via monkeypatch;
confirms it is wired supplementary-only, exactly like S3D."""

from datetime import datetime, timezone

from app.config import settings
from app.schemas import DetectionResult
from app.services import pipeline
from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor


def test_temporal_predictor_disabled_by_default():
    assert settings.temporal_prediction_adapter == "none"
    assert pipeline.get_temporal_predictor() is None


def test_maybe_predict_temporal_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: None)
    assert pipeline.maybe_predict_temporal("cam-1", "standing", datetime.now(timezone.utc)) is None


def test_maybe_predict_temporal_records_and_predicts(monkeypatch):
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)
    camera_id = "cam-temporal-1"
    t0 = datetime.now(timezone.utc)

    first = pipeline.maybe_predict_temporal(camera_id, "standing", t0)
    assert first["predicted_label"] is None  # cold start
    assert first["history_length"] == 0

    # Predicts from "standing" (recorded by call 1) before "walking" (this call's own
    # label) is recorded -- no standing->X transition exists yet either, so still None.
    second = pipeline.maybe_predict_temporal(camera_id, "walking", t0)
    assert second["based_on_label"] == "standing"  # prior label, not the one just passed in
    assert second["predicted_label"] is None
    assert second["history_length"] == 1

    # Now standing->walking has been recorded once (by call 2's observe). Predicting
    # from "walking" (the current last label) still has no recorded successor of its
    # own yet -- walking->X has never been observed.
    third = pipeline.maybe_predict_temporal(camera_id, "standing", t0)
    assert third["based_on_label"] == "walking"
    assert third["predicted_label"] is None
    assert third["history_length"] == 2

    # Now walking->standing has been recorded once too. Predicting from "standing"
    # again finally has real history: standing->walking happened once before.
    fourth = pipeline.maybe_predict_temporal(camera_id, "walking", t0)
    assert fourth["based_on_label"] == "standing"
    assert fourth["predicted_label"] == "walking"
    assert fourth["confidence"] == 1.0
    assert fourth["history_length"] == 3


def test_prediction_never_leaks_the_current_observation_into_itself(monkeypatch):
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)
    camera_id = "cam-temporal-2"
    t0 = datetime.now(timezone.utc)

    # Feed a real sequence: standing -> walking -> standing -> walking
    pipeline.maybe_predict_temporal(camera_id, "standing", t0)
    pipeline.maybe_predict_temporal(camera_id, "walking", t0)
    pipeline.maybe_predict_temporal(camera_id, "standing", t0)
    result = pipeline.maybe_predict_temporal(camera_id, "walking", t0)

    # At the moment this 4th call's prediction was made, history was
    # [standing, walking, standing] (this call's own "walking" not yet recorded) --
    # based_on_label must be "standing" (the label before this one), not "walking".
    assert result["based_on_label"] == "standing"


def test_temporal_prediction_never_reaches_the_threat_engine(monkeypatch):
    """Mirrors the S3D isolation test: even with a temporal predictor enabled and
    primed to predict something threat-vocabulary-looking, evaluate_window()'s
    threat_score must be identical to the geometry-heuristic-only result."""
    predictor = MarkovTemporalPredictor()
    # Prime it so predicting from "standing" (the label the geometry heuristic will
    # actually report below) suggests "fighting_candidate" -- an adversarial setup to
    # prove this can't leak into scoring. Sequence: standing->fighting_candidate
    # (records the transition we want found), then ->standing again (so the *current*
    # last label is "standing" by the time evaluate_window() runs its own prediction).
    cam = "cam-temporal-isolation"
    now = datetime.now(timezone.utc)
    predictor.observe(cam, "standing", now)
    predictor.observe(cam, "fighting_candidate", now)
    predictor.observe(cam, "standing", now)
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get("cam-temporal-isolation")
    window.add(
        datetime.now(timezone.utc),
        [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")],
    )

    result = pipeline.evaluate_window("cam-temporal-isolation")
    assert result is not None
    action_result, _, _ = result

    assert action_result.label == "standing"  # geometry heuristic's real reading
    assert action_result.threat_score == 0.05  # unaffected by the primed prediction
    assert action_result.temporal_prediction is not None
    assert action_result.temporal_prediction["predicted_label"] == "fighting_candidate"  # surfaced...
    assert action_result.temporal_prediction["predicted_label"] != action_result.label  # ...never merged


def test_temporal_prediction_is_none_when_disabled():
    window = pipeline.buffer_store.get("cam-temporal-off")
    window.add(
        datetime.now(timezone.utc),
        [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")],
    )
    result = pipeline.evaluate_window("cam-temporal-off")
    assert result is not None
    action_result, _, _ = result
    assert action_result.temporal_prediction is None
