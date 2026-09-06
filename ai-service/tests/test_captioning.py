from app.action_recognition.base import ActionObservation
from app.captioning.template_adapter import TemplateCaptioner
from app.schemas import DetectionResult


def test_caption_mentions_person_count():
    captioner = TemplateCaptioner()
    detections = [
        DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="DEMO"),
        DetectionResult(object="person", confidence=0.9, bounding_box=[20, 20, 30, 30], mode="DEMO"),
    ]
    action = ActionObservation(label="standing", confidence=0.6, mode="DEMO", metrics={})
    caption = captioner.caption(detections, action)
    assert "Two people" in caption


def test_caption_mentions_other_objects():
    captioner = TemplateCaptioner()
    detections = [
        DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="DEMO"),
        DetectionResult(object="car", confidence=0.9, bounding_box=[20, 20, 30, 30], mode="DEMO"),
    ]
    action = ActionObservation(label="walking", confidence=0.6, mode="DEMO", metrics={})
    caption = captioner.caption(detections, action)
    assert "car" in caption


def test_caption_handles_no_people():
    captioner = TemplateCaptioner()
    action = ActionObservation(label="no_activity", confidence=0.6, mode="DEMO", metrics={})
    caption = captioner.caption([], action)
    assert "No significant activity" in caption


# --- person count uses the deduplicated action metric, not a raw recount (Phase 2P) --
#
# Regression tests for the real incident in docs/phase2o-live-system-audit.md: 3
# overlapping YOLO boxes for one person previously produced a caption reading "4 people
# in close proximity" even where the fix for the score itself (demo_heuristic.py) had
# already corrected the underlying person count.


def test_caption_uses_deduplicated_person_count_when_available():
    captioner = TemplateCaptioner()
    # Four raw "person" detections (e.g. overlapping duplicate boxes for one person),
    # but the action observation's own avg_person_count -- already deduplicated by
    # DemoHeuristicActionRecognizer -- says there's actually only 1.
    detections = [
        DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")
        for _ in range(4)
    ]
    action = ActionObservation(label="standing", confidence=0.55, mode="DEMO", metrics={"avg_person_count": 1.0})
    caption = captioner.caption(detections, action)
    assert "One person" in caption
    assert "4 people" not in caption
    assert "people" not in caption or "One person" in caption


def test_caption_rounds_a_fractional_average_person_count():
    captioner = TemplateCaptioner()
    action = ActionObservation(label="walking", confidence=0.55, mode="DEMO", metrics={"avg_person_count": 1.6})
    caption = captioner.caption([], action)
    assert "Two people" in caption


def test_caption_falls_back_to_raw_count_when_metric_is_absent():
    # An observation that never sets avg_person_count (e.g. one built without going
    # through DemoHeuristicActionRecognizer) must still fall back to a raw count of the
    # detections actually passed in, rather than crashing or reporting zero people.
    captioner = TemplateCaptioner()
    detections = [
        DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL"),
        DetectionResult(object="knife", confidence=0.9, bounding_box=[20, 20, 30, 30], mode="REAL"),
    ]
    action = ActionObservation(label="standing", confidence=0.9, mode="REAL", metrics={})
    caption = captioner.caption(detections, action)
    assert "One person" in caption
