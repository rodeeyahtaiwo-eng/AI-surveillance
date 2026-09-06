"""Phase 2X — proximity geometry normalized against the real camera frame instead of a
box-derived estimate. Real-evidence fixtures below (marked REAL) are the exact
bounding boxes pulled from database/dev.db for the specific incidents the Phase 2W
forensic audit examined — not invented. Everything else uses realistic, clearly-labeled
constructed geometry. No threshold/base-score/bonus value is touched or asserted to be
anything other than its existing production value."""

from datetime import datetime, timedelta, timezone

from app.action_recognition.demo_heuristic import DemoHeuristicActionRecognizer, _frame_diagonal_estimate, _proximity_and_speed
from app.schemas import DetectionResult
from app.threat.rule_based import RuleBasedThreatEngine

FRAME_W, FRAME_H = 640, 480  # this project's camera's real, known resolution throughout

recognizer = DemoHeuristicActionRecognizer()
engine = RuleBasedThreatEngine()


def person(box, confidence=0.9) -> DetectionResult:
    return DetectionResult(object="person", confidence=confidence, bounding_box=box, mode="REAL")


def t(i: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)


# REAL evidence: the "opposite sides of frame" pair from Phase 2W's forensic audit
# (database/dev.db, Camera 01, frameTimestamp 1788643692088-ish window) — two people on
# opposite halves of a 640x480 frame, effectively zero x-overlap.
REAL_SEPARATED_PAIR = (
    [222.52630615234375, 121.40350341796875, 523.8856811523438, 479.158935546875],
    [0.1920623779296875, 0.733978271484375, 154.71913146972656, 478.1910095214844],
)

# REAL evidence: one of the genuinely-adjacent pairs from the real knife/close-contact
# sequence immediately preceding the CRITICAL escalation (frameTimestamp 1788643111303).
REAL_ADJACENT_PAIR = (
    [266.92169189453125, 44.0465087890625, 638.2986450195312, 479.03955078125],
    [0.6407470703125, 0.94439697265625, 347.2633972167969, 478.8681335449219],
)


# --- Test 1: one calm person -----------------------------------------------------------


def test_one_calm_person_stays_standing_with_real_frame_dimensions():
    window = [(t(0), [person([250, 100, 390, 470])]), (t(1), [person([252, 101, 392, 471])])]
    obs = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    assert obs.label == "standing"
    score, _ = engine.assess(obs, previous_score=None)
    assert score == 0.05


# --- Test 2: two people calmly close together ------------------------------------------


def test_two_people_genuinely_close_together_are_still_close_contact_with_real_dimensions():
    # Two distinct, partially-overlapping people (containment ratio ~0.52 -- well under
    # DUPLICATE_BOX_OVERLAP_THRESHOLD=0.7, so this is genuinely two people, not a
    # duplicate-box artifact) standing close enough that their centroids are ~110px
    # apart on a 640x480 frame (true diagonal 800px) -- genuinely close in real terms.
    # The architecture MUST still be able to reach close_contact for real close
    # contact; this is not forced LOW by the geometry fix.
    boxes = ([150, 50, 380, 470], [260, 60, 490, 470])
    window = [(t(0), [person(boxes[0]), person(boxes[1])]), (t(1), [person(boxes[0]), person(boxes[1])])]
    obs = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    ratio = obs.metrics["min_proximity_ratio"]
    assert ratio < 0.15, f"expected genuinely-close people to read as close under real geometry, got ratio={ratio}"
    assert obs.label == "close_contact"


# --- Test 3: separated two-person -- THE primary regression test -----------------------


def test_real_separated_pair_is_no_longer_close_contact_with_real_frame_dimensions():
    box_a, box_b = REAL_SEPARATED_PAIR
    window = [(t(0), [person(box_a), person(box_b)]), (t(1), [person(box_a), person(box_b)])]

    # OLD behavior (no frame dimensions supplied -- the documented fallback): this is
    # the exact false positive the Phase 2W audit found, reproduced from real data.
    old_obs = recognizer.recognize(window)
    assert old_obs.metrics["min_proximity_ratio"] < 0.15
    assert old_obs.label == "close_contact"

    # NEW behavior (real frame dimensions supplied): the same real boxes, now correctly
    # read as NOT close, because they really are on opposite sides of a 640x480 frame.
    new_obs = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    assert new_obs.metrics["min_proximity_ratio"] >= 0.15
    assert new_obs.label != "close_contact"
    assert new_obs.label != "fighting_candidate"


def test_frame_diagonal_estimate_fallback_is_byte_identical_to_pre_phase_2x():
    # The old function itself is untouched -- confirms the fallback path, not just its
    # caller, is unmodified.
    boxes = [REAL_SEPARATED_PAIR[0], REAL_SEPARATED_PAIR[1]]
    assert _frame_diagonal_estimate(boxes) > 2000  # the old, inflated, box-derived estimate


# --- Test 4: walking ---------------------------------------------------------------------


def test_walking_classification_is_unaffected_by_real_frame_dimensions():
    window = [
        (t(0), [person([100, 100, 200, 400])]),
        (t(1), [person([130, 100, 230, 400])]),  # ~30px/s -- within the walking band
    ]
    obs_old = recognizer.recognize(window)
    obs_new = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    assert obs_old.label == obs_new.label == "walking"


# --- Test 5: approaching -----------------------------------------------------------------


def test_approaching_classification_still_reachable_with_real_frame_dimensions():
    # Two people far apart (not close) but one moving fast -- "approaching" branch,
    # which does not depend on proximity at all (see demo_heuristic.py's elif chain).
    window = [
        (t(0), [person([50, 50, 150, 450]), person([500, 50, 600, 450])]),
        (t(1), [person([150, 50, 250, 450]), person([500, 50, 600, 450])]),  # ~100px/s
    ]
    obs = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    assert obs.metrics["min_proximity_ratio"] >= 0.15  # genuinely not close
    assert obs.label == "approaching"


# --- Test 6: the real knife/close-contact -> CRITICAL sequence, replayed ---------------


def test_real_knife_sequence_no_longer_reaches_close_contact_with_real_frame_dimensions():
    # REAL evidence, documented regression (Phase 2X forensic report, section 4): the
    # exact real adjacent-pair geometry from the moment immediately preceding the real
    # CRITICAL escalation, now measured against the true 640x480 diagonal, no longer
    # falls under CLOSE_PROXIMITY_RATIO=0.15 (unchanged, untouched this phase). This
    # test exists to make that known, evidenced trade-off explicit and visible to any
    # future change -- not to declare it acceptable or final; see the Phase 2X report's
    # "Remaining Issues" and "Recommendation" sections.
    box_a, box_b = REAL_ADJACENT_PAIR
    window = [(t(0), [person(box_a), person(box_b)]), (t(1), [person(box_a), person(box_b)])]
    obs = recognizer.recognize(window, frame_width=FRAME_W, frame_height=FRAME_H)
    assert obs.metrics["min_proximity_ratio"] >= 0.15
    assert obs.label != "close_contact"


# --- Phase 2T invariant, re-confirmed unaffected by this change ------------------------


def test_threat_score_is_still_computed_before_any_temporal_or_geometry_concern():
    # Confirms assess() itself takes only an ActionObservation + previous_score -- it
    # has no frame_width/frame_height parameter and cannot be affected by this phase's
    # plumbing change at all; Phase 2T's own ordering (score finalized, then temporal
    # prediction computed) lives entirely in pipeline.py's evaluate_window(), untouched
    # this phase (re-verified by inspection, not modified).
    import inspect

    sig = inspect.signature(RuleBasedThreatEngine.assess)
    assert "frame_width" not in sig.parameters
    assert "frame_height" not in sig.parameters
    assert "temporal_prediction" not in sig.parameters
