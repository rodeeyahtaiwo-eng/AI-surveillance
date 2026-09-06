"""Tests that BLIP, when wired in via CAPTION_ADAPTER=blip, receives a real frame from
the existing clip buffer through evaluate_window() -- and that its caption never
influences threat_score (captions are structurally write-only outputs of the pipeline;
this confirms that remains true after Phase 2R)."""

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

    pipeline.evaluate_window(camera_id)  # kicks off the (fake, but backgrounded) generation
    captioner.wait_for_pending_generation(camera_id)
    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    assert "a person is standing in a room" in action_result.description
    assert "Grounded detections: person." in action_result.description
    # Confirms a real frame reached the captioner (not None) -- BLIP actually ran.
    assert processor.last_image is not None


def test_blip_caption_text_never_influences_threat_score(monkeypatch):
    from app.captioning.blip_adapter import BlipCaptioner

    class DangerousWordsProcessor(FakeBlipProcessor):
        def decode(self, token_ids, skip_special_tokens=True):
            # Adversarial: a caption that mentions "gun" and "fighting" -- must not
            # cause any escalation, since captions are never read by the threat engine.
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

    pipeline.evaluate_window(camera_id)  # kicks off the (fake, but backgrounded) generation
    captioner.wait_for_pending_generation(camera_id)
    result = pipeline.evaluate_window(camera_id)
    assert result is not None
    action_result, _, _ = result

    # The real detector saw one stationary person -> "standing" -> 0.05, regardless of
    # what BLIP's hallucinated caption text says.
    assert action_result.label == "standing"
    assert action_result.threat_score == 0.05
    assert "gun" in action_result.description  # the caption IS still shown, transparently
    assert "Grounded detections: person." in action_result.description  # but "gun" is not in the grounded list
