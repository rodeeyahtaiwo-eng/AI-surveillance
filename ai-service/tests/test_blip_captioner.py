"""Unit tests for BlipCaptioner using injected fake processor/model — never loads the
real ~990MB checkpoint, matching this project's existing adapter-testing pattern.
Includes the mandatory hallucination-safety test from docs/phase2r-integration.md
Part 12 Test D, reproducing the exact Phase 2Q mirror-hallucination scenario."""

from datetime import datetime, timedelta, timezone

import numpy as np
import torch

from app.action_recognition.base import ActionObservation
from app.captioning.blip_adapter import BlipCaptioner
from app.schemas import DetectionResult


class FakeBlipProcessor:
    def __init__(self):
        self.decode_calls = 0

    def __call__(self, images, return_tensors):
        return {"pixel_values": torch.zeros(1, 3, 8, 8)}

    def decode(self, token_ids, skip_special_tokens=True):
        self.decode_calls += 1
        return f"fake caption #{self.decode_calls}"


class FakeBlipModel:
    def generate(self, **kwargs):
        return torch.zeros(1, 4, dtype=torch.long)

    def eval(self):
        pass


class HallucinatingProcessor(FakeBlipProcessor):
    """Reproduces the exact Phase 2Q result verbatim."""

    def decode(self, token_ids, skip_special_tokens=True):
        self.decode_calls += 1
        return "a woman in a white dress is standing in front of a mirror"


def person(confidence: float = 0.9) -> DetectionResult:
    return DetectionResult(object="person", confidence=confidence, bounding_box=[0, 0, 10, 10], mode="REAL")


def frame() -> np.ndarray:
    return np.zeros((16, 16, 3), dtype=np.uint8)


def action() -> ActionObservation:
    return ActionObservation(label="standing", confidence=0.55, mode="DEMO", metrics={})


def test_never_requires_real_weights():
    fake_model = FakeBlipModel()
    captioner = BlipCaptioner(processor=FakeBlipProcessor(), model=fake_model)
    assert captioner._model is fake_model


def test_generates_a_caption_and_appends_grounded_detections():
    # Phase 2AB: generation is now dispatched to a background thread so caption()
    # never blocks (see module docstring); the FIRST call for a cold camera still
    # returns the "pending" placeholder immediately -- wait for the background
    # generation, then confirm a second call now sees the real text.
    captioner = BlipCaptioner(processor=FakeBlipProcessor(), model=FakeBlipModel())
    first = captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")
    assert "caption pending" in first  # nothing generated yet -- returned instantly
    captioner.wait_for_pending_generation("cam-1")
    second = captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")
    assert "fake caption #1" in second
    assert "Grounded detections: person." in second


def test_no_grounded_objects_still_produces_a_clear_none_marker():
    captioner = BlipCaptioner(processor=FakeBlipProcessor(), model=FakeBlipModel())
    result = captioner.caption([], action(), frame=frame(), camera_id="cam-1")
    assert "Grounded detections: none." in result


def test_no_frame_falls_back_without_calling_the_model():
    processor = FakeBlipProcessor()
    captioner = BlipCaptioner(processor=processor, model=FakeBlipModel())
    result = captioner.caption([person()], action(), frame=None, camera_id="cam-1")
    assert processor.decode_calls == 0
    assert "caption pending" in result


def test_cooldown_reuses_the_previous_caption_instead_of_regenerating():
    processor = FakeBlipProcessor()
    captioner = BlipCaptioner(processor=processor, model=FakeBlipModel())

    captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")
    captioner.wait_for_pending_generation("cam-1")
    first = captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")  # cooldown active now
    second = captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")

    assert processor.decode_calls == 1  # BLIP was only actually invoked once
    assert "fake caption #1" in first
    assert "fake caption #1" in second  # reused, not regenerated


def test_cooldown_is_tracked_per_camera_not_globally():
    processor = FakeBlipProcessor()
    captioner = BlipCaptioner(processor=processor, model=FakeBlipModel())

    captioner.caption([person()], action(), frame=frame(), camera_id="cam-a")
    captioner.caption([person()], action(), frame=frame(), camera_id="cam-b")
    captioner.wait_for_pending_generation("cam-a")
    captioner.wait_for_pending_generation("cam-b")

    assert processor.decode_calls == 2  # a different camera's cooldown must not block this one


def test_a_generation_failure_falls_back_to_the_previous_caption_and_never_raises():
    class FailingModel(FakeBlipModel):
        def generate(self, **kwargs):
            raise RuntimeError("simulated inference failure")

    captioner = BlipCaptioner(processor=FakeBlipProcessor(), model=FakeBlipModel())
    captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")  # seed a cached caption
    captioner.wait_for_pending_generation("cam-1")
    captioner._model = FailingModel()
    captioner._last_eval_at_by_camera["cam-1"] = datetime.now(timezone.utc) - timedelta(hours=1)  # clear cooldown

    captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")  # kicks off the failing generation
    captioner.wait_for_pending_generation("cam-1")
    result = captioner.caption([person()], action(), frame=frame(), camera_id="cam-1")
    assert "fake caption #1" in result  # fell back to the cached one, did not crash


# --- Mandatory hallucination-safety test (Part 12 Test D) ----------------------------
#
# Reproduces the exact Phase 2Q result verbatim: BLIP invented a mirror that was not
# actually in the image. Confirms the grounding policy holds for this exact case.


def test_hallucinated_object_is_never_inserted_into_structured_detections():
    captioner = BlipCaptioner(processor=HallucinatingProcessor(), model=FakeBlipModel())
    real_detections = [person()]  # the real detector found a person -- no mirror, ever

    captioner.caption(real_detections, action(), frame=frame(), camera_id="cam-1")
    captioner.wait_for_pending_generation("cam-1")
    result = captioner.caption(real_detections, action(), frame=frame(), camera_id="cam-1")

    # 1. BLIP still produced its (hallucinated) caption.
    assert "mirror" in result

    # 2. The hallucinated object must not appear in the grounded/detector-confirmed list.
    grounded = captioner.get_last_result("cam-1")["grounded_objects"]
    assert "mirror" not in grounded
    assert grounded == ["person"]

    # 3. The input detections list itself is untouched -- caption() never mutates it or
    #    fabricates a new DetectionResult from caption text.
    assert real_detections == [person()]
    assert all(isinstance(d, DetectionResult) for d in real_detections)
    assert not any(d.object == "mirror" for d in real_detections)

    # 4. The raw caption remains visible/auditable, separately from the grounded list.
    last = captioner.get_last_result("cam-1")
    assert last["source"] == "BLIP"
    assert "mirror" in last["raw_caption"]
    assert last["grounded_objects"] == ["person"]

    # 5. The display string keeps the two visibly separate, not blended into one
    #    implicitly-verified sentence.
    assert "Grounded detections: person." in result
