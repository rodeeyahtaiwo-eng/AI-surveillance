"""Unit tests for MarkovTemporalPredictor — pure Python, no model, no I/O."""

from datetime import datetime, timedelta, timezone

from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor


def t(i: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)


def test_cold_start_returns_no_prediction():
    predictor = MarkovTemporalPredictor()
    result = predictor.predict_next("cam-1")
    assert result.predicted_label is None
    assert result.confidence == 0.0
    assert result.history_length == 0
    assert "cold start" in result.rationale.lower()


def test_single_observation_has_no_successor_yet():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-1", "standing", t(0))

    result = predictor.predict_next("cam-1")

    assert result.predicted_label is None
    assert result.based_on_label == "standing"
    assert "never been followed" in result.rationale


def test_predicts_the_most_frequent_real_successor():
    predictor = MarkovTemporalPredictor()
    # standing -> walking happens both times "standing" occurs with a successor.
    sequence = ["standing", "walking", "standing", "walking", "standing"]
    for i, label in enumerate(sequence):
        predictor.observe("cam-1", label, t(i))

    result = predictor.predict_next("cam-1")

    assert result.predicted_label == "walking"  # standing -> walking happened every time
    assert result.confidence == 1.0
    assert result.based_on_label == "standing"
    assert result.history_length == len(sequence)


def test_does_not_simply_copy_the_current_action():
    # The whole point: the current (most recent) label is "walking" -- observed
    # history says walking is always followed by standing, never by walking again. A
    # predictor that just copied the current action would wrongly say "walking"; the
    # real transition-based prediction must say "standing" instead.
    predictor = MarkovTemporalPredictor()
    for label in ["standing", "walking", "standing", "walking"]:
        predictor.observe("cam-1", label, t(0))

    result = predictor.predict_next("cam-1")

    assert result.based_on_label == "walking"  # the current label, for reference
    assert result.predicted_label == "standing"  # NOT "walking" (current) repeated
    assert result.predicted_label != result.based_on_label


def test_distribution_is_normalized_and_matches_the_top_prediction():
    predictor = MarkovTemporalPredictor()
    # standing -> walking (x3), standing -> no_activity (x1)
    predictor.observe("cam-1", "standing", t(0))
    for _ in range(3):
        predictor.observe("cam-1", "walking", t(0))
        predictor.observe("cam-1", "standing", t(0))
    predictor.observe("cam-1", "no_activity", t(0))
    predictor.observe("cam-1", "standing", t(0))

    result = predictor.predict_next("cam-1")

    assert abs(sum(result.distribution.values()) - 1.0) < 1e-9
    assert result.distribution[result.predicted_label] == result.confidence


def test_predict_next_does_not_see_a_transition_before_it_is_observed():
    # Ordering guarantee: predict_next() must reflect history strictly BEFORE the
    # current event -- observe() for the current event must not have run yet when a
    # caller wants "what did we expect before seeing this."
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-1", "standing", t(0))
    predictor.observe("cam-1", "walking", t(1))

    # At this point, history is [standing, walking]. Predicting from "walking" (the
    # current last label) must show no successor yet, since walking->X was never
    # observed -- confirms nothing was leaked from a not-yet-made observation.
    result = predictor.predict_next("cam-1")
    assert result.predicted_label is None
    assert result.based_on_label == "walking"


def test_history_is_tracked_independently_per_camera():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-a", "standing", t(0))
    predictor.observe("cam-a", "walking", t(1))

    result_b = predictor.predict_next("cam-b")
    assert result_b.predicted_label is None
    assert result_b.history_length == 0

    result_a = predictor.predict_next("cam-a")
    assert result_a.based_on_label == "walking"
    assert result_a.history_length == 2


def test_source_identifier_is_present_and_stable():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-1", "standing", t(0))
    result = predictor.predict_next("cam-1")
    assert result.source == "temporal_markov_v1"


def test_rationale_and_generated_at_are_always_populated():
    predictor = MarkovTemporalPredictor()
    result = predictor.predict_next("cam-1")
    assert result.rationale
    assert result.generated_at is not None


# --- prediction -> outcome validation (Phase 2T) -------------------------------------


def test_first_ever_observation_has_no_outcome_to_resolve():
    predictor = MarkovTemporalPredictor()
    outcome = predictor.observe("cam-1", "standing", t(0))
    assert outcome is None  # nothing was predicted before this, since predict_next() was never called


def test_observe_without_a_preceding_predict_next_call_has_no_outcome():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-1", "standing", t(0))
    # No predict_next() call here -- go straight to another observe().
    outcome = predictor.observe("cam-1", "walking", t(1))
    assert outcome is None


def test_matching_prediction_is_recorded_as_matched():
    predictor = MarkovTemporalPredictor()
    # Teach it: standing -> walking, always.
    predictor.observe("cam-1", "standing", t(0))
    predictor.observe("cam-1", "walking", t(1))
    predictor.observe("cam-1", "standing", t(2))
    predictor.observe("cam-1", "walking", t(3))

    prediction = predictor.predict_next("cam-1")  # current=walking... wait, standing
    assert prediction.based_on_label == "walking"
    # walking has no recorded successor yet in this short sequence -- extend it so
    # there's something to compare.
    outcome = predictor.observe("cam-1", "standing", t(4))
    assert outcome is not None
    assert outcome.actual_label == "standing"

    # Now predict from "standing" (a real, established transition: standing->walking).
    prediction2 = predictor.predict_next("cam-1")
    assert prediction2.predicted_label == "walking"
    outcome2 = predictor.observe("cam-1", "walking", t(5))  # matches the prediction
    assert outcome2 is not None
    assert outcome2.predicted_label == "walking"
    assert outcome2.actual_label == "walking"
    assert outcome2.matched is True


def test_mismatched_prediction_is_recorded_as_not_matched():
    predictor = MarkovTemporalPredictor()
    # Teach it: standing -> walking, always (3 times).
    for _ in range(3):
        predictor.observe("cam-1", "standing", t(0))
        predictor.observe("cam-1", "walking", t(0))

    prediction = predictor.predict_next("cam-1")  # based_on_label = "walking"
    outcome_setup = predictor.observe("cam-1", "standing", t(0))
    assert outcome_setup is not None  # resolves the "walking" prediction (no successor yet, so None predicted)

    prediction2 = predictor.predict_next("cam-1")  # based_on_label = "standing" -> predicts "walking"
    assert prediction2.predicted_label == "walking"

    # But the ACTUAL next real observation is something else entirely.
    outcome = predictor.observe("cam-1", "no_activity", t(0))
    assert outcome is not None
    assert outcome.predicted_label == "walking"
    assert outcome.actual_label == "no_activity"
    assert outcome.matched is False


def test_outcome_matched_is_none_when_the_prior_prediction_itself_had_no_label():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-1", "standing", t(0))  # no transitions recorded yet
    prediction = predictor.predict_next("cam-1")
    assert prediction.predicted_label is None  # "standing" has no recorded successor

    outcome = predictor.observe("cam-1", "walking", t(1))
    assert outcome is not None
    assert outcome.predicted_label is None
    assert outcome.matched is None  # nothing was actually predicted, so no match/mismatch judgment is made


def test_outcome_tracking_is_independent_per_camera():
    predictor = MarkovTemporalPredictor()
    predictor.observe("cam-a", "standing", t(0))
    predictor.observe("cam-a", "walking", t(1))
    predictor.predict_next("cam-a")  # pending prediction for cam-a only

    # A completely separate camera's observe() must not be affected by cam-a's pending prediction.
    outcome_b = predictor.observe("cam-b", "standing", t(0))
    assert outcome_b is None
