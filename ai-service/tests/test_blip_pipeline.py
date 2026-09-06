"""Tests that BLIP, when wired in via CAPTION_ADAPTER=blip, receives a real frame from
the existing clip buffer through evaluate_window() -- and that RuleBasedThreatEngine's
own scoring math never reads caption text (captions remain structurally write-only
inputs to the engine itself; confirmed true since Phase 2R). Phase 2AC added one
narrow, separate exception at the pipeline-orchestration level (not inside the engine):
a raw-caption weapon-keyword match can raise threat_score to a modest, clearly-logged
floor (CAPTION_KEYWORD_FLOOR) as a fallback for the general detector's known recall
gaps -- see test_blip_caption_keyword_only_raises_the_narrow_corroboration_floor_not_the_engine_score
below and app/threat/rule_based.py's CAPTION_WEAPON_KEYWORDS docstring."""

from datetime import datetime, timezone

import numpy as np
import torch

from app.schemas import DetectionResult
from app.services import pipeline


class FakeBlipProcessor:
    def __call__(self, images, return_tensors):
        self.last_image = images
        return {"pixel_values": torch.zeros(1, 3, 8, 8)}

    def decode(self, token_ids, skip_special_tokens=True):
        return "a person is standing in a room"


class FakeBlipModel:
    def generate(self, **kwargs):
        return torch.zeros(1, 4, dtype=torch.long)


def test_evaluate_window_passes_a_real_buffered_frame_to_the_captioner(monkeypatch):
    from app.captioning.blip_adapter import BlipCaptioner

    processor = FakeBlipProcessor()
    captioner = BlipCaptioner(processor=processor, model=FakeBlipModel())
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)

    camera_id = "cam-blip-pipeline"
    distinctive_frame = np.full((4, 4, 3), 77, dtype=np.uint8)  # distinctive pixel value
    pipeline.clip_buffer_store.get(camera_id).add(distinctive_frame)

    window = pipeline.buffer_store.get(camera_id)
    window.add(
        datetime.now(timezone.utc),
        [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")],
    )

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert "a person is standing in a room" in action_result.description
    assert "Grounded detections: person." in action_result.description
    # Confirms a real frame reached the captioner (not None) -- BLIP actually ran.
    assert processor.last_image is not None


def test_blip_caption_keyword_only_raises_the_narrow_corroboration_floor_not_the_engine_score(monkeypatch):
    """Phase 2AC narrowed this invariant: RuleBasedThreatEngine.assess() itself still
    never reads caption text (unchanged, still verified directly by
    tests/test_threat_engine.py, whose ThreatAssessmentAdapter.assess() signature takes
    no caption parameter at all) -- but app/services/pipeline.py now applies a separate,
    deliberate, clearly-logged CAPTION_KEYWORD_FLOOR (0.40) AFTER assess() returns, when
    the raw caption matches an explicit weapon/violence keyword and a person is present.
    This is a confirmed, intentional fix for the general detector's real recall gaps
    (see the current-state audit) -- not a bug. It must still never let caption text
    alone reach HIGH/CRITICAL, and must remain visibly distinct from grounded-detection
    evidence in the rationale."""
    from app.captioning.blip_adapter import BlipCaptioner

    class DangerousWordsProcessor(FakeBlipProcessor):
        def decode(self, token_ids, skip_special_tokens=True):
            # Adversarial: a caption that mentions "gun" and "fighting" -- both real
            # entries in CAPTION_WEAPON_KEYWORDS.
            return "a person appears to be fighting with a gun"

    captioner = BlipCaptioner(processor=DangerousWordsProcessor(), model=FakeBlipModel())
    monkeypatch.setattr(pipeline, "get_caption_adapter", lambda: captioner)

    camera_id = "cam-blip-danger-words"
    pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype=np.uint8))
    window = pipeline.buffer_store.get(camera_id)
    window.add(
        datetime.now(timezone.utc),
        [DetectionResult(object="person", confidence=0.9, bounding_box=[0, 0, 10, 10], mode="REAL")],
    )

    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    # The real detector saw one stationary person -> geometry heuristic alone still
    # reads "standing"; the score is then raised only by the separate, narrow
    # corroboration step, not by RuleBasedThreatEngine's own base/bonus math.
    assert action_result.label == "standing"
    assert action_result.threat_score == 0.40  # CAPTION_KEYWORD_FLOOR -- MEDIUM, not HIGH/CRITICAL
    assert "CAPTION-CORROBORATION" in action_result.rationale  # visibly distinct, auditable tag
    assert "gun" in action_result.description  # the caption IS still shown, transparently
    assert "Grounded detections: person." in action_result.description  # but "gun" is not in the grounded list
