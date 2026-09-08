"""Phase 2AH — tests for the SEPARATE, stronger CAPTION_KEYWORD_PERSISTED_FLOOR
escalation in app/services/pipeline.py's evaluate_window(), which fires only when a
weapon/violence keyword appears across CAPTION_KEYWORD_PERSISTENCE_MIN_HITS (2)
genuinely distinct caption generations within CAPTION_KEYWORD_PERSISTENCE_WINDOW_SECONDS
(45s) — as opposed to the existing single-mention CAPTION_KEYWORD_FLOOR (Phase 2AC),
which fires on just one. Never loads a real YOLO/BLIP model."""

from datetime import datetime, timedelta, timezone

import numpy as np
import torch

from app.captioning.blip_adapter import BlipCaptioner
from app.schemas import DetectionResult
from app.services import pipeline
from app.threat.rule_based import CAPTION_KEYWORD_FLOOR, CAPTION_KEYWORD_PERSISTED_FLOOR


def person(confidence: float = 0.9) -> DetectionResult:
    return DetectionResult(object="person", confidence=confidence, bounding_box=[0, 0, 50, 50], mode="REAL")


class QueuedProcessor:
    """Returns each text in `texts` in order, one per decode() call — lets a test
    control exactly what BLIP "generates" on each fresh (non-cooldown) call."""

    def __init__(self, texts):
        self._texts = list(texts)
        self.decode_calls = 0

    def __call__(self, images, return_tensors):
        return {"pixel_values": torch.zeros(1, 3, 8, 8)}

    def decode(self, token_ids, skip_special_tokens=True):
        text = self._texts[min(self.decode_calls, len(self._texts) - 1)]
        self.decode_calls += 1
        return text


class FakeBlipModel:
    def generate(self, **kwargs):
        return torch.zeros(1, 4, dtype=torch.long)


def clear_cooldown(captioner: BlipCaptioner, camera_id: str) -> None:
    """Forces BlipCaptioner's own cooldown to have already expired, simulating a
    genuinely fresh BLIP generation on the next caption() call — same technique as
    tests/test_blip_captioner.py's cooldown tests."""
    captioner._last_eval_at_by_camera[camera_id] = datetime.now(timezone.utc) - timedelta(hours=1)


def test_two_distinct_matching_captions_reach_the_persisted_escalation(monkeypatch):
    camera_id = "cam-persist-distinct"
    captioner = BlipCaptioner(
        processor=QueuedProcessor(["a man holding a knife in his hand", "a woman with a large knife nearby"]),
        model=FakeBlipModel(),
    )
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype="uint8"))

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [person()])
    first = pipeline.evaluate_window(camera_id)
    assert first is not None
    assert first[0].threat_score == CAPTION_KEYWORD_FLOOR  # single-mention floor only, first time

    clear_cooldown(captioner, camera_id)  # force a genuinely fresh second generation
    window.add(datetime.now(timezone.utc) + timedelta(seconds=1), [person()])
    second = pipeline.evaluate_window(camera_id)
    assert second is not None
    action_result, _, _ = second

    assert action_result.threat_score == CAPTION_KEYWORD_PERSISTED_FLOOR
    assert "CAPTION-CORROBORATION-PERSISTED" in action_result.rationale
    assert "knife" in action_result.rationale


def test_a_single_mention_never_reaches_the_persisted_escalation(monkeypatch):
    camera_id = "cam-persist-single"
    captioner = BlipCaptioner(
        processor=QueuedProcessor(["a woman holding a knife in her hand"]),
        model=FakeBlipModel(),
    )
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype="uint8"))

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [person()])
    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == CAPTION_KEYWORD_FLOOR  # 0.40, not 0.65
    assert "CAPTION-CORROBORATION-PERSISTED" not in action_result.rationale


def test_identical_repeated_caption_text_is_treated_as_one_cached_observation_not_two(monkeypatch):
    """Simulates BLIP's own 20s cooldown cache reusing one generation across two window
    evaluations -- the identical text must NOT be double-counted as independent
    reconfirmation (that would be a single-mention trust jump wearing a persistence
    costume, exactly what this feature exists to avoid)."""
    camera_id = "cam-persist-cached-repeat"
    captioner = BlipCaptioner(
        processor=QueuedProcessor(["a woman holding a knife in her hand"]),
        model=FakeBlipModel(),
    )
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype="uint8"))

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [person()])
    pipeline.evaluate_window(camera_id)

    # Second evaluation while still on BLIP's own cooldown (not cleared) -- reuses the
    # exact same cached raw_caption text, exactly as real production behavior does.
    window.add(datetime.now(timezone.utc) + timedelta(seconds=1), [person()])
    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert action_result.threat_score == CAPTION_KEYWORD_FLOOR  # still 0.40, not 0.65
    assert captioner._processor.decode_calls == 1  # confirms BLIP only actually ran once


def test_persistence_requires_a_person_present_just_like_the_single_mention_floor(monkeypatch):
    camera_id = "cam-persist-no-person"
    captioner = BlipCaptioner(
        processor=QueuedProcessor(["a knife on a table", "a knife on a table again"]),
        model=FakeBlipModel(),
    )
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype="uint8"))

    window = pipeline.buffer_store.get(camera_id)
    window.add(datetime.now(timezone.utc), [])  # no person at all
    first = pipeline.evaluate_window(camera_id)
    assert first is not None
    assert first[0].threat_score == 0.0  # no_activity, no person -> floors never engage

    clear_cooldown(captioner, camera_id)
    window.add(datetime.now(timezone.utc) + timedelta(seconds=1), [])
    second = pipeline.evaluate_window(camera_id)
    assert second is not None
    assert second[0].threat_score == 0.0
    assert "CAPTION-CORROBORATION" not in second[0].rationale
