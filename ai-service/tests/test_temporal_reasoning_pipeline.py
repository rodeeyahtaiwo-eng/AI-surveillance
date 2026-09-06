"""Phase 2T — temporal escalation reasoning and prediction/outcome validation, at the
pipeline level. Uses the REAL production MarkovTemporalPredictor together with
evaluate_window(), never a real YOLO/BLIP/S3D model. Transitions used below
(approaching->close_contact, close_contact->fighting_candidate) are grounded in the
real historical data — see scripts/evaluate_phase2t_temporal_walkforward.py's output:
these two are well-evidenced (3/3 and 3/4 respectively); "walking->approaching" is
NOT (0/45) and is deliberately not used here."""

from datetime import datetime, timedelta, timezone

from app.schemas import DetectionResult
from app.services import pipeline
from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor


def person(x1: float = 100) -> DetectionResult:
    return DetectionResult(object="person", confidence=0.9, bounding_box=[x1, 100, x1 + 40, 200], mode="REAL")


def two_close_people():
    # Mirrors the Phase 2P-corrected fixture: genuinely distinct, close together.
    return [
        DetectionResult(object="person", confidence=0.9, bounding_box=[100, 100, 140, 200], mode="REAL"),
        DetectionResult(object="person", confidence=0.9, bounding_box=[135, 105, 175, 205], mode="REAL"),
    ]


def knife(confidence: float = 0.7) -> DetectionResult:
    return DetectionResult(object="knife", confidence=confidence, bounding_box=[0, 0, 50, 50], mode="REAL")


# --- grounded transitions (real evidence, not an idealized story) --------------------


def test_approaching_to_close_contact_is_a_real_grounded_transition(monkeypatch):
    # 3/3 in the real historical data (see script output).
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)
    camera_id = "cam-2t-grounded-1"

    predictor.observe(camera_id, "approaching", datetime.now(timezone.utc))
    predictor.observe(camera_id, "close_contact", datetime.now(timezone.utc))
    predictor.observe(camera_id, "approaching", datetime.now(timezone.utc))
    predictor.observe(camera_id, "close_contact", datetime.now(timezone.utc))

    prediction = predictor.predict_next(camera_id)
    assert prediction.based_on_label == "close_contact"
    # We haven't taught close_contact->fighting_candidate yet in this local test setup.


def test_close_contact_to_fighting_candidate_is_a_real_grounded_transition(monkeypatch):
    # 3/4 in the real historical data.
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)
    camera_id = "cam-2t-grounded-2"

    for _ in range(3):
        predictor.observe(camera_id, "close_contact", datetime.now(timezone.utc))
        predictor.observe(camera_id, "fighting_candidate", datetime.now(timezone.utc))
    predictor.observe(camera_id, "close_contact", datetime.now(timezone.utc))

    prediction = predictor.predict_next(camera_id)
    assert prediction.predicted_label == "fighting_candidate"
    assert prediction.confidence == 1.0


def test_walking_to_approaching_is_honestly_not_predicted_because_data_does_not_support_it(monkeypatch):
    # Explicit, honest negative test: this transition does NOT occur in the real
    # historical data (0/45) -- confirm the predictor does not invent it either, if
    # this project's own local history never taught it.
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)
    camera_id = "cam-2t-ungrounded"

    predictor.observe(camera_id, "walking", datetime.now(timezone.utc))
    prediction = predictor.predict_next(camera_id)
    assert prediction.predicted_label is None  # no history taught it this transition either


# --- explainable output: rationale distinguishes observed evidence from prediction ---


def test_rationale_appends_temporal_context_phrased_as_a_prediction_not_a_fact(monkeypatch):
    predictor = MarkovTemporalPredictor()
    # Teach standing->walking, then return to "standing" as the current/last label, so
    # evaluate_window()'s own predict_next() call (current="standing") finds it.
    predictor.observe("cam-2t-rationale", "standing", datetime.now(timezone.utc))
    predictor.observe("cam-2t-rationale", "walking", datetime.now(timezone.utc))  # records standing->walking
    predictor.observe("cam-2t-rationale", "standing", datetime.now(timezone.utc))  # last label back to "standing"
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get("cam-2t-rationale")
    window.add(datetime.now(timezone.utc), [person()])

    result = pipeline.evaluate_window("cam-2t-rationale")
    assert result is not None
    action_result, _, _ = result

    assert "Temporal context:" in action_result.rationale
    assert "model predicts" in action_result.rationale  # explicitly phrased as a prediction
    assert "walking" in action_result.rationale  # the predicted label, based on standing->walking taught above
    # Never phrased as something that already happened:
    assert "fighting detected" not in action_result.rationale.lower()
    assert "violence detected" not in action_result.rationale.lower()


def test_no_temporal_context_appended_when_there_is_no_prediction(monkeypatch):
    predictor = MarkovTemporalPredictor()  # cold start -- no history at all
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get("cam-2t-no-prediction")
    window.add(datetime.now(timezone.utc), [person()])

    result = pipeline.evaluate_window("cam-2t-no-prediction")
    assert result is not None
    action_result, _, _ = result

    assert "Temporal context:" not in action_result.rationale


# --- prediction alone must never create or raise a threat ----------------------------


def test_a_fighting_candidate_prediction_alone_does_not_raise_the_score(monkeypatch):
    # Adversarial: prime the predictor so it predicts "fighting_candidate" (the
    # highest-scoring label) with high confidence, then confirm a genuinely calm,
    # single-person window still scores exactly as it would without the predictor.
    predictor = MarkovTemporalPredictor()
    cam = "cam-2t-prediction-not-proof"
    predictor.observe(cam, "standing", datetime.now(timezone.utc))
    predictor.observe(cam, "fighting_candidate", datetime.now(timezone.utc))
    predictor.observe(cam, "standing", datetime.now(timezone.utc))
    predictor.observe(cam, "fighting_candidate", datetime.now(timezone.utc))
    predictor.observe(cam, "standing", datetime.now(timezone.utc))  # last label = standing
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get(cam)
    window.add(datetime.now(timezone.utc), [person()])  # one calm, stationary person

    result = pipeline.evaluate_window(cam)
    assert result is not None
    action_result, _, _ = result

    assert action_result.label == "standing"
    assert action_result.threat_score == 0.05  # completely unaffected by the primed prediction
    assert action_result.temporal_prediction["predicted_label"] == "fighting_candidate"  # surfaced...
    assert "model predicts 'fighting_candidate'" in action_result.rationale  # ...as a prediction...
    assert action_result.threat_score < 0.65  # ...never treated as proof of an already-occurring threat


# --- prediction/outcome surfaced through the pipeline API ----------------------------


def test_previous_prediction_outcome_is_surfaced_and_correctly_marked_matched(monkeypatch):
    # A stationary single person reliably reads "standing" every time (same fixture
    # used throughout this suite) -- teaches standing->standing, so the next
    # prediction (standing->standing, 100% confidence) is guaranteed to match.
    predictor = MarkovTemporalPredictor()
    cam = "cam-2t-outcome-match"
    predictor.observe(cam, "standing", datetime.now(timezone.utc))
    predictor.observe(cam, "standing", datetime.now(timezone.utc))
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get(cam)
    window.add(datetime.now(timezone.utc), [person()])  # geometry heuristic reads "standing"

    result = pipeline.evaluate_window(cam)
    assert result is not None
    action_result, _, _ = result

    assert action_result.label == "standing"
    outcome = action_result.temporal_prediction["previous_prediction_outcome"]
    assert outcome is not None
    assert outcome["predicted_label"] == "standing"
    assert outcome["actual_label"] == "standing"
    assert outcome["matched"] is True


def test_previous_prediction_outcome_has_no_judgment_on_the_very_first_evaluation(monkeypatch):
    # evaluate_window() always calls predict_next() immediately before observe() (see
    # maybe_predict_temporal()), so even on a brand-new camera's first-ever evaluation,
    # SOME outcome dict is produced (predict_next() always stashes a pending entry,
    # even a "no prediction possible" one) -- but it correctly carries no judgment:
    # predicted_label=None and matched=None, since nothing was actually predicted yet.
    predictor = MarkovTemporalPredictor()  # brand new, zero history
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    window = pipeline.buffer_store.get("cam-2t-outcome-first-ever")
    window.add(datetime.now(timezone.utc), [person()])

    result = pipeline.evaluate_window("cam-2t-outcome-first-ever")
    assert result is not None
    action_result, _, _ = result

    outcome = action_result.temporal_prediction["previous_prediction_outcome"]
    assert outcome is not None
    assert outcome["predicted_label"] is None
    assert outcome["matched"] is None


# --- normal static scene stays LOW, even with temporal + S3D-style signals present ----


def test_normal_static_scene_stays_low_with_temporal_predictor_enabled(monkeypatch):
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    cam = "cam-2t-normal-scene"
    window = pipeline.buffer_store.get(cam)
    for i in range(3):
        window.add(datetime.now(timezone.utc) + timedelta(seconds=i), [person()])
        result = pipeline.evaluate_window(cam)

    assert result is not None
    action_result, _, _ = result
    assert action_result.label == "standing"
    assert action_result.threat_score == 0.05


# --- Phase 2S knife pathway remains functional with temporal predictor also enabled ---


def test_knife_pathway_still_works_with_temporal_predictor_enabled(monkeypatch):
    predictor = MarkovTemporalPredictor()
    monkeypatch.setattr(pipeline, "get_temporal_predictor", lambda: predictor)

    cam = "cam-2t-knife-with-temporal"
    window = pipeline.buffer_store.get(cam)
    t0 = datetime.now(timezone.utc)
    window.add(t0, [person(), knife()])
    window.add(t0 + timedelta(seconds=1), [person(), knife()])

    result = pipeline.evaluate_window(cam)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.65  # Phase 2AB-recalibrated confirmed-knife floor, unaffected by temporal predictor being on
    assert "knife detected" in action_result.rationale
