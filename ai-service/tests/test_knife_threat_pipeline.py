"""Pipeline-level tests for the Phase 2S knife-evidence wiring in
app/services/pipeline.py's evaluate_window() — the persistence gating (not the scoring
math itself, see tests/test_threat_engine.py for that) — plus explicit isolation from
BLIP captions. Never loads a real YOLO/BLIP model."""

from datetime import datetime, timedelta, timezone

import numpy as np
import torch

from app.schemas import DetectionResult
from app.services import pipeline


def knife(confidence: float = 0.7) -> DetectionResult:
    return DetectionResult(object="knife", confidence=confidence, bounding_box=[0, 0, 50, 50], mode="REAL")


def person(x1: float = 100, confidence: float = 0.9) -> DetectionResult:
    return DetectionResult(object="person", confidence=confidence, bounding_box=[x1, 100, x1 + 40, 200], mode="REAL")


def test_single_isolated_knife_frame_raises_to_the_cautious_unconfirmed_floor():
    # Phase 2AB: a single, not-yet-persisted knife sighting now gets the small,
    # explicitly cautious "unconfirmed" floor (0.35, below MEDIUM) rather than nothing
    # at all -- live testing found a knife that produced zero signal until the 2nd
    # confirming frame felt invisible to the demo. The CONFIRMED/persisted tier (0.65)
    # correctly does NOT fire here -- only one frame has been seen.
    camera_id = "cam-knife-isolated"
    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [person(), knife()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.35
    assert "unconfirmed" in action_result.rationale.lower()


def test_knife_persisted_across_two_frames_within_the_window_elevates_the_score():
    camera_id = "cam-knife-persisted"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    window.add(t0, [person(), knife()])
    window.add(t0 + timedelta(seconds=1), [person(), knife()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.65  # standing + knife(persisted, Phase 2AB HIGH floor) + person
    assert "knife" in action_result.rationale.lower()


def test_knife_frame_outside_the_persistence_window_falls_back_to_the_unconfirmed_floor():
    camera_id = "cam-knife-too-old"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    # First knife hit is outside knife_persistence_window_seconds (4s default) of the
    # second -- only 1 of 2 falls within the trailing window, same rule as firearm's.
    from app.config import settings

    window.add(t0 - timedelta(seconds=settings.knife_persistence_window_seconds + 5), [person(), knife()])
    window.add(t0, [person(), knife()])
    window.prune(settings.sequence_window_seconds)

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    # The CONFIRMED/persisted tier (0.65) correctly does not fire (only 1 of 2 hits is
    # within the trailing window) -- but a knife genuinely is visible in the current
    # window, so the smaller "unconfirmed" floor (0.35) correctly still applies. This
    # is the Phase 2AB behavior change from this test's original 0.05 expectation.
    assert action_result.threat_score == 0.35


def test_knife_persisted_with_no_person_anywhere_does_not_elevate():
    camera_id = "cam-knife-no-person"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    window.add(t0, [knife()])
    window.add(t0 + timedelta(seconds=1), [knife()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.0  # "no_activity" (avg_persons < 0.5) + knife, no person -> unscored


# --- regression: BLIP-induced request latency must not defeat persistence -------------
#
# Real incident discovered during this phase's own live E2E test: BLIP's multi-second
# synchronous cost delays each subsequent frame's own recorded timestamp (since
# video-processing/the live test client only sends the next frame after receiving the
# previous response), so a persistence check measured against wall-clock "now" at CHECK
# time found real, closely-spaced knife detections "too old". See
# app/common/frame_buffer.py's count_recent_frames_with_object_as_of() and
# docs/phase2s-threat-reasoning.md.


def test_knife_persistence_survives_a_large_gap_between_now_and_the_last_frame():
    # Simulates exactly what was observed live: two knife-containing frames close
    # together BY THEIR OWN TIMESTAMPS, but the check running long after (as it would
    # if an intervening BLIP call had stalled the response for several seconds).
    camera_id = "cam-knife-blip-latency-regression"
    window = pipeline.buffer_store.get(camera_id)
    frame_time = datetime.now(timezone.utc) - timedelta(seconds=30)  # long ago by wall-clock now
    window.add(frame_time, [person(), knife()])
    window.add(frame_time + timedelta(seconds=1), [person(), knife()])  # 1s apart, by their own timestamps

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    # Must still be scored as persisted -- the two knife frames are only 1s apart by
    # their own timestamps, regardless of how much real wall-clock time has passed
    # since. Before the Phase 2S fix, this would have failed (0.05, not persisted)
    # because the old code measured against datetime.now() instead of the buffered
    # frames' own latest timestamp. 0.65 is the Phase 2AB-recalibrated confirmed floor
    # (was 0.45).
    assert action_result.threat_score == 0.65


# --- isolation from BLIP captions ------------------------------------------------------


class HallucinatingKnifeProcessor:
    def __call__(self, images, return_tensors):
        return {"pixel_values": torch.zeros(1, 3, 8, 8)}

    def decode(self, token_ids, skip_special_tokens=True):
        return "a person appears to be holding a large knife"


class FakeBlipModel:
    def generate(self, **kwargs):
        return torch.zeros(1, 4, dtype=torch.long)


def test_blip_caption_mentioning_a_knife_never_creates_knife_evidence_without_real_detection(monkeypatch):
    from app.captioning.blip_adapter import BlipCaptioner

    captioner = BlipCaptioner(processor=HallucinatingKnifeProcessor(), model=FakeBlipModel())
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)

    camera_id = "cam-knife-blip-hallucination"
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype=np.uint8))
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    # NO real "knife" detection anywhere -- only a person, twice.
    window.add(t0, [person()])
    window.add(t0 + timedelta(seconds=1), [person()])

    pipeline.evaluate_window(camera_id)  # kicks off the (fake, but backgrounded) generation
    captioner.wait_for_pending_generation(camera_id)
    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert "knife" in action_result.description.lower()  # the caption IS shown, transparently
    assert action_result.threat_score == 0.05  # but it never elevated the score
    assert "Grounded detections: person." in action_result.description  # knife is not in the grounded list


# --- normal scene sanity check ----------------------------------------------------------


def test_normal_person_no_knife_stays_at_the_low_baseline():
    camera_id = "cam-knife-normal-scene"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    window.add(t0, [person()])
    window.add(t0 + timedelta(seconds=1), [person()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.label == "standing"
    assert action_result.threat_score == 0.05
