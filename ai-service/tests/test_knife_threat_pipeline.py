"""Pipeline-level tests for the Phase 2S knife-evidence wiring in
app/services/pipeline.py's evaluate_window() — the persistence gating (not the scoring
math itself, see tests/test_threat_engine.py for that) — plus the caption/detection
grounding boundary: a hallucinated caption is never turned into a fabricated
DetectionResult, though Phase 2AC's narrow CAPTION_KEYWORD_FLOOR fallback (see
app/threat/rule_based.py) does now deliberately let a raw-caption weapon-keyword match
raise threat_score on its own, separately from and visibly distinct from grounded
detection evidence. Never loads a real YOLO/BLIP model."""

from datetime import datetime, timedelta, timezone

import numpy as np
import torch

from app.schemas import DetectionResult
from app.services import pipeline


def knife(confidence: float = 0.7) -> DetectionResult:
    return DetectionResult(object="knife", confidence=confidence, bounding_box=[0, 0, 50, 50], mode="REAL")


def person(x1: float = 100, confidence: float = 0.9) -> DetectionResult:
    return DetectionResult(object="person", confidence=confidence, bounding_box=[x1, 100, x1 + 40, 200], mode="REAL")


def test_single_knife_frame_now_elevates_the_score_phase_2ad():
    """Phase 2AD lowered knife_persistence_min_hits from 2 to 1 (CONFIRMED GAP: the
    one real historical knife-threat scenario in this system's history produced exactly
    1 knife-class detection in its window, never 2, so the old K=2 gate never engaged).
    A single knife+person detection now satisfies persistence directly -- this replaces
    this test's previous "must not elevate" assertion. See app/config.py's
    knife_persistence_min_hits docstring for the full noise-check reasoning behind why
    K=1 was judged safe."""
    camera_id = "cam-knife-isolated"
    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [person(), knife()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.45  # standing + knife(persisted, K=1) + person
    assert "knife" in action_result.rationale.lower()


def test_knife_persisted_across_two_frames_within_the_window_elevates_the_score():
    camera_id = "cam-knife-persisted"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    window.add(t0, [person(), knife()])
    window.add(t0 + timedelta(seconds=1), [person(), knife()])

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.45  # standing + knife(persisted) + person
    assert "knife" in action_result.rationale.lower()


def test_knife_frame_outside_the_persistence_window_does_not_count():
    """With knife_persistence_min_hits=1 (Phase 2AD), a single RECENT knife hit is
    already sufficient on its own -- so this test's original 2-old-vs-1-recent setup
    would trivially pass regardless of the time-window cutoff. Re-targeted at what
    actually still needs covering: a knife hit that falls OUTSIDE the trailing
    knife_persistence_window_seconds (4s) but still survives the broader
    sequence_window_seconds buffer prune (6s) must still not count, even under K=1 --
    i.e. the time-window arithmetic in count_recent_frames_with_object_as_of() is
    unaffected by the K change. The only knife detection here is 5s old (excluded by
    the 4s persistence window, but young enough to survive the 6s buffer prune); the
    recent frame has a person but no knife."""
    camera_id = "cam-knife-too-old"
    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    from app.config import settings

    assert settings.knife_persistence_window_seconds < settings.sequence_window_seconds
    old_offset = (settings.knife_persistence_window_seconds + settings.sequence_window_seconds) / 2
    window.add(t0 - timedelta(seconds=old_offset), [person(), knife()])
    window.add(t0, [person()])  # recent frame -- no knife
    window.prune(settings.sequence_window_seconds)

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == 0.05  # the only knife hit is outside the trailing window


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
    # since. Before the fix, this would have failed (0.05, not persisted) because the
    # old code measured against datetime.now() instead of the buffered frames' own
    # latest timestamp.
    assert action_result.threat_score == 0.45


# --- isolation from BLIP captions ------------------------------------------------------


class HallucinatingKnifeProcessor:
    def __call__(self, images, return_tensors):
        return {"pixel_values": torch.zeros(1, 3, 8, 8)}

    def decode(self, token_ids, skip_special_tokens=True):
        return "a person appears to be holding a large knife"


class FakeBlipModel:
    def generate(self, **kwargs):
        return torch.zeros(1, 4, dtype=torch.long)


def test_blip_caption_mentioning_a_knife_triggers_the_corroboration_floor_but_never_fabricates_grounded_evidence(
    monkeypatch,
):
    """Phase 2AC: a caption naming a weapon with no real detection now raises
    threat_score to the modest CAPTION_KEYWORD_FLOOR (0.40) as a deliberate,
    clearly-logged fallback for the general detector's confirmed recall gaps -- this
    replaces this test's previous "must never elevate" assertion (see
    app/threat/rule_based.py's CAPTION_WEAPON_KEYWORDS docstring for the full
    reasoning). What remains true and is still verified here: the caption is never
    turned into a fabricated DetectionResult, and "knife" never appears in the
    detector-grounded object list -- only in the separately-labeled caption text and
    the visibly-tagged corroboration rationale."""
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

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert "knife" in action_result.description.lower()  # the caption IS shown, transparently
    assert action_result.threat_score == 0.40  # CAPTION_KEYWORD_FLOOR, via the narrow fallback path
    assert "CAPTION-CORROBORATION" in action_result.rationale  # visibly distinct from grounded evidence
    assert "Grounded detections: person." in action_result.description  # knife is still not in the grounded list


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
