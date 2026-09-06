from app.action_recognition.base import ActionObservation
from app.threat.rule_based import BASE_SCORE_BY_ACTION, RuleBasedThreatEngine


def make_observation(label: str, **metrics: float) -> ActionObservation:
    return ActionObservation(label=label, confidence=0.6, mode="DEMO", metrics=metrics)


def test_no_activity_scores_zero():
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(make_observation("no_activity"), previous_score=None)
    assert score == 0.0
    assert "no_activity" in rationale


def test_fighting_candidate_scores_higher_than_standing():
    engine = RuleBasedThreatEngine()
    standing_score, _ = engine.assess(make_observation("standing"), previous_score=None)
    fighting_score, _ = engine.assess(make_observation("fighting_candidate"), previous_score=None)
    assert fighting_score > standing_score


def test_close_proximity_adds_bonus():
    engine = RuleBasedThreatEngine()
    base_score, _ = engine.assess(make_observation("close_contact"), previous_score=None)
    close_score, _ = engine.assess(
        make_observation("close_contact", min_proximity_ratio=0.05), previous_score=None
    )
    assert close_score > base_score


def test_sustained_escalation_adds_bonus_and_is_capped_at_one():
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(
        make_observation("fighting_candidate", min_proximity_ratio=0.05, movement_speed_px_s=200),
        previous_score=0.9,
    )
    assert score <= 1.0
    assert "escalation" in rationale.lower() or "rising" in rationale.lower()


def test_weapon_detected_is_no_longer_a_recognized_action_label():
    # Phase 2V: firearm detection removed -- "weapon_detected" has no special-cased
    # base score any more and falls through to the generic unknown-label default (0.1),
    # exactly like any other string nothing in the pipeline can actually produce.
    assert "weapon_detected" not in BASE_SCORE_BY_ACTION
    engine = RuleBasedThreatEngine()
    score, _ = engine.assess(make_observation("weapon_detected"), previous_score=None)
    assert score == 0.1


def test_score_is_always_within_bounds():
    engine = RuleBasedThreatEngine()
    for label in ["no_activity", "standing", "walking", "running", "approaching", "close_contact", "fighting_candidate", "unknown_label"]:
        score, _ = engine.assess(make_observation(label, min_proximity_ratio=0.01, movement_speed_px_s=500), previous_score=0.95)
        assert 0.0 <= score <= 1.0


# --- Knife evidence floor (Phase 2S) --------------------------------------------------
#
# See docs/phase2s-threat-reasoning.md for the investigation this implements: a real
# knife scenario previously scored 0.05/LOW because no knife-aware rule existed at all.


def test_knife_alone_no_persistence_does_not_elevate():
    # knife_persisted defaults to absent/0.0 -- an isolated, unconfirmed sighting.
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(make_observation("standing", avg_person_count=1.0), previous_score=None)
    assert score == 0.05  # unchanged from the plain "standing" base score
    assert "knife" not in rationale.lower()


def test_knife_persisted_with_no_person_does_not_elevate():
    # Explicit Phase 2O requirement: a knife with no person/context is not a threat.
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(
        make_observation("no_activity", knife_persisted=1.0, avg_person_count=0.0), previous_score=None
    )
    assert score == 0.0  # unchanged from plain no_activity
    assert "no corroborating person" in rationale


def test_knife_persisted_with_person_raises_to_the_medium_floor():
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(
        make_observation("standing", knife_persisted=1.0, avg_person_count=1.0), previous_score=None
    )
    assert score == 0.45
    assert score > 0.05  # materially higher than the unarmed baseline
    assert "knife detected" in rationale
    assert "raised to 0.45" in rationale


def test_knife_persisted_with_close_contact_raises_to_the_high_floor():
    engine = RuleBasedThreatEngine()
    score, rationale = engine.assess(
        make_observation("close_contact", knife_persisted=1.0, avg_person_count=2.0), previous_score=None
    )
    assert score == 0.70
    assert "close_contact" in rationale


def test_knife_persisted_with_fighting_candidate_does_not_reduce_the_existing_higher_score():
    # fighting_candidate's own base (0.70) already meets the aggressive-context floor
    # (0.70) -- the knife evidence must never LOWER a score that's already there on its
    # own merits, and any additional bonus (proximity/movement) on top must survive.
    engine = RuleBasedThreatEngine()
    without_knife, _ = engine.assess(
        make_observation("fighting_candidate", min_proximity_ratio=0.05, movement_speed_px_s=200),
        previous_score=None,
    )
    with_knife, _ = engine.assess(
        make_observation(
            "fighting_candidate", min_proximity_ratio=0.05, movement_speed_px_s=200,
            knife_persisted=1.0, avg_person_count=2.0,
        ),
        previous_score=None,
    )
    assert with_knife >= without_knife


def test_knife_floor_is_a_ceiling_not_a_stack_with_proximity_bonus():
    # Confirms this is a MAX/floor operation, not additive: close_contact + proximity
    # bonus (0.50) + knife floor (0.70) must land exactly at 0.70, not 1.20 or 0.50+0.70.
    engine = RuleBasedThreatEngine()
    score, _ = engine.assess(
        make_observation("close_contact", min_proximity_ratio=0.05, knife_persisted=1.0, avg_person_count=1.0),
        previous_score=None,
    )
    assert score == 0.70
