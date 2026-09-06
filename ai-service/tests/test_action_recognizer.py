from datetime import datetime, timedelta, timezone

from app.action_recognition.demo_heuristic import DemoHeuristicActionRecognizer
from app.schemas import DetectionResult


def person(x1: float, y1: float, x2: float, y2: float) -> DetectionResult:
    return DetectionResult(object="person", confidence=0.9, bounding_box=[x1, y1, x2, y2], mode="DEMO")


def test_empty_window_is_no_activity():
    recognizer = DemoHeuristicActionRecognizer()
    result = recognizer.recognize([])
    assert result.label == "no_activity"


def test_stationary_single_person_is_standing():
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    window = [(t0 + timedelta(seconds=i), [person(100, 100, 150, 200)]) for i in range(4)]
    result = recognizer.recognize(window)
    assert result.label == "standing"
    assert result.mode == "DEMO"


def test_fast_moving_single_person_is_running():
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    window = [
        (t0, [person(0, 0, 50, 100)]),
        (t0 + timedelta(seconds=1), [person(500, 0, 550, 100)]),
    ]
    result = recognizer.recognize(window)
    assert result.label == "running"


def test_two_people_close_together_is_close_contact_or_fighting():
    # Phase 2P: revised from the original [100,100,130,200]/[105,100,135,200] pair,
    # which had a box-overlap ("containment") ratio of 0.83 -- too close to the 0.876-
    # 0.990 range measured in the real duplicate-person-box incident (see
    # demo_heuristic.DUPLICATE_BOX_OVERLAP_THRESHOLD) to safely tell apart from a
    # dedup-worthy duplicate. These two boxes are near each other (centroids ~35px
    # apart, well within the proximity threshold) but overlap only ~0.12 -- realistic
    # for two actually-distinct people standing close together, and clearly below
    # DUPLICATE_BOX_OVERLAP_THRESHOLD (0.7), so dedup must NOT collapse them.
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    window = [
        (t0 + timedelta(seconds=i), [person(100, 100, 140, 200), person(135, 105, 175, 205)])
        for i in range(4)
    ]
    result = recognizer.recognize(window)
    assert result.label in ("close_contact", "fighting_candidate")
    assert result.metrics["min_proximity_ratio"] < 0.15
    assert result.metrics["avg_person_count"] == 2  # both people preserved, not deduped


# --- duplicate/overlapping-box dedup (Phase 2P) --------------------------------------
#
# Regression tests for the real incident traced in
# docs/phase2o-live-system-audit.md: one person filling most of the frame produced 3
# overlapping YOLO "person" boxes, each counted as a separate person, triggering a
# false close_contact / 0.50 / MEDIUM alert.


def test_identical_person_boxes_count_as_one_person():
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    same_box = (100, 100, 400, 400)
    window = [
        (t0 + timedelta(seconds=i), [person(*same_box), person(*same_box), person(*same_box)])
        for i in range(4)
    ]
    result = recognizer.recognize(window)
    assert result.metrics["avg_person_count"] == 1
    assert result.label not in ("close_contact", "fighting_candidate", "approaching")


def test_real_incident_overlapping_boxes_do_not_trigger_close_contact():
    # The exact three bounding boxes from the real production incident
    # (database/dev.db, Alert.id=cmto9wqwp00lhwstfmq46f3ei, 2026-09-05 11:02:10 UTC) --
    # one person, three overlapping YOLO candidate boxes, measured containment ratios
    # 0.876 / 0.939 / 0.990 (see DUPLICATE_BOX_OVERLAP_THRESHOLD's comment). Before this
    # fix, this exact input produced avg_person_count=4 (with a 4th near-duplicate box
    # in the same live window) and a close_contact/0.50/MEDIUM alert.
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    real_boxes = [
        (67.86367797851562, 93.37162780761719, 384.8619079589844, 478.54180908203125),
        (40.87774658203125, 141.3841552734375, 544.8960571289062, 479.65655517578125),
        (71.139404296875, 66.63616943359375, 613.236328125, 479.422119140625),
    ]
    window = [
        (t0 + timedelta(seconds=i), [person(*b) for b in real_boxes])
        for i in range(4)
    ]
    result = recognizer.recognize(window)
    assert result.metrics["avg_person_count"] == 1
    assert result.label not in ("close_contact", "fighting_candidate", "approaching")


def test_partially_overlapping_boxes_representing_one_person_are_deduplicated():
    # A looser and a tighter crop of the same person (one box includes more of an
    # outstretched arm) -- containment ~0.8, above the 0.7 threshold, below a plain-IoU
    # reading of the same pair would suggest.
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    window = [
        (t0 + timedelta(seconds=i), [person(100, 100, 300, 400), person(100, 100, 250, 400)])
        for i in range(4)
    ]
    result = recognizer.recognize(window)
    assert result.metrics["avg_person_count"] == 1


def test_genuinely_separate_people_are_not_deduplicated():
    # Two people far enough apart that neither their overlap nor their proximity ratio
    # should ever be mistaken for duplicates or for close contact.
    recognizer = DemoHeuristicActionRecognizer()
    t0 = datetime.now(timezone.utc)
    window = [
        (t0 + timedelta(seconds=i), [person(0, 0, 50, 100), person(500, 300, 550, 400)])
        for i in range(4)
    ]
    result = recognizer.recognize(window)
    assert result.metrics["avg_person_count"] == 2
    assert result.metrics["min_proximity_ratio"] >= 0.15
    assert result.label not in ("close_contact", "fighting_candidate")


def test_deduplicate_boxes_keeps_highest_confidence_box():
    from app.action_recognition.demo_heuristic import _deduplicate_boxes

    low = DetectionResult(object="person", confidence=0.4, bounding_box=[100, 100, 400, 400], mode="DEMO")
    high = DetectionResult(object="person", confidence=0.9, bounding_box=[100, 100, 390, 390], mode="DEMO")
    result = _deduplicate_boxes([low, high])
    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_deduplicate_boxes_is_not_person_specific():
    # The helper itself doesn't filter by class -- callers are responsible for that.
    # Confirms it works generically on whatever DetectionResult list it's given.
    from app.action_recognition.demo_heuristic import _deduplicate_boxes

    a = DetectionResult(object="car", confidence=0.5, bounding_box=[0, 0, 100, 100], mode="REAL")
    b = DetectionResult(object="car", confidence=0.6, bounding_box=[0, 0, 95, 95], mode="REAL")
    assert len(_deduplicate_boxes([a, b])) == 1


def test_overlap_ratio_matches_hand_computed_values():
    from app.action_recognition.demo_heuristic import _overlap_ratio

    # Non-overlapping boxes.
    assert _overlap_ratio([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    # Identical boxes.
    assert _overlap_ratio([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    # Real incident's boxes A and C: intersection 120822, smaller area (A) 122079.
    a = [67.86367797851562, 93.37162780761719, 384.8619079589844, 478.54180908203125]
    c = [71.139404296875, 66.63616943359375, 613.236328125, 479.422119140625]
    assert _overlap_ratio(a, c) > 0.85
