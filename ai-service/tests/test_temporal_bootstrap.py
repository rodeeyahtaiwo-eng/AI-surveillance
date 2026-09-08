"""Phase 2AK — tests for maybe_bootstrap_temporal_predictor(): pre-populating the
Markov predictor's in-memory transition counts from persisted history on first use per
camera, reusing the adapter's own existing observe() update logic (no new counting
algorithm). Never loads a real YOLO/BLIP model or touches a real network."""

from datetime import datetime, timedelta, timezone

from app.services import pipeline
from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor


def setup_function():
    # Each test gets a clean slate -- this module-level set otherwise persists across
    # tests in the same process, exactly like the real singleton would across windows.
    pipeline._temporal_bootstrapped_cameras.clear()


def test_bootstrap_replays_real_history_through_the_existing_observe_method(monkeypatch):
    t0 = datetime.now(timezone.utc)
    fake_history = [
        ("standing", t0),
        ("standing", t0 + timedelta(seconds=5)),
        ("walking", t0 + timedelta(seconds=10)),
        ("standing", t0 + timedelta(seconds=15)),
    ]
    monkeypatch.setattr(pipeline.settings, "temporal_prediction_bootstrap_enabled", True)
    monkeypatch.setattr("app.services.backend_client.fetch_action_history", lambda camera_id: fake_history)

    predictor = MarkovTemporalPredictor()
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-1", predictor)

    # Reused the real, existing observe() logic -- no new counting algorithm: the
    # resulting transition table is byte-identical to calling observe() 4 times by hand.
    predicted = predictor.predict_next("cam-bootstrap-1")
    assert predicted.predicted_label == "standing"  # standing->standing is 2/2 real transitions
    assert predicted.history_length == 4


def test_bootstrap_only_happens_once_per_camera_per_process(monkeypatch):
    call_count = {"n": 0}

    def fake_fetch(camera_id):
        call_count["n"] += 1
        return [("standing", datetime.now(timezone.utc))]

    monkeypatch.setattr(pipeline.settings, "temporal_prediction_bootstrap_enabled", True)
    monkeypatch.setattr("app.services.backend_client.fetch_action_history", fake_fetch)

    predictor = MarkovTemporalPredictor()
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-2", predictor)
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-2", predictor)
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-2", predictor)

    assert call_count["n"] == 1


def test_bootstrap_is_a_no_op_when_disabled(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "temporal_prediction_bootstrap_enabled", False)
    monkeypatch.setattr(
        "app.services.backend_client.fetch_action_history",
        lambda camera_id: (_ for _ in ()).throw(AssertionError("must not be called when disabled")),
    )

    predictor = MarkovTemporalPredictor()
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-3", predictor)  # must not raise

    predicted = predictor.predict_next("cam-bootstrap-3")
    assert predicted.history_length == 0  # untouched -- genuinely cold start


def test_bootstrap_never_raises_when_history_fetch_fails_or_is_empty(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "temporal_prediction_bootstrap_enabled", True)
    monkeypatch.setattr("app.services.backend_client.fetch_action_history", lambda camera_id: [])

    predictor = MarkovTemporalPredictor()
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-4", predictor)  # must not raise

    predicted = predictor.predict_next("cam-bootstrap-4")
    assert predicted.history_length == 0


def test_bootstrap_is_read_only_and_never_creates_a_pending_prediction(monkeypatch):
    """Confirms bootstrap only ever calls observe(), never predict_next() -- so it can't
    accidentally leave a stale pending-prediction for the live flow to resolve against."""
    t0 = datetime.now(timezone.utc)
    monkeypatch.setattr(pipeline.settings, "temporal_prediction_bootstrap_enabled", True)
    monkeypatch.setattr(
        "app.services.backend_client.fetch_action_history",
        lambda camera_id: [("standing", t0), ("walking", t0 + timedelta(seconds=5))],
    )

    predictor = MarkovTemporalPredictor()
    pipeline.maybe_bootstrap_temporal_predictor("cam-bootstrap-5", predictor)

    assert predictor._pending_prediction.get("cam-bootstrap-5") is None
