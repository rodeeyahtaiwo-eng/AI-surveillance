"""Unit tests for S3DKineticsAdapter using an injected fake model — never loads the
real torchvision checkpoint, matching this project's existing pattern (see
tests/test_x3d_violence_adapter.py)."""

import numpy as np
import pytest
import torch

from app.action_recognition.s3d_kinetics_adapter import NUM_FRAMES, S3DKineticsAdapter


def fake_preprocess(clip: torch.Tensor) -> torch.Tensor:
    """Stands in for S3D_Weights.KINETICS400_V1.transforms() — the adapter just needs
    *some* tensor to unsqueeze and feed to the model; this test never exercises real
    resize/normalize math."""
    return clip.float()


class FakeS3DModel:
    def __init__(self, logits: torch.Tensor):
        self.logits = logits

    def __call__(self, batch):
        return self.logits

    def eval(self):
        pass


def make_frames(n: int = NUM_FRAMES, h: int = 32, w: int = 32):
    return [np.zeros((h, w, 3), dtype=np.uint8) for _ in range(n)]


def test_returns_top1_as_kinetics_prefixed_label():
    logits = torch.zeros(1, 5)
    logits[0, 2] = 10.0  # class index 2 dominates after softmax
    categories = ["a", "b", "running", "d", "e"]
    adapter = S3DKineticsAdapter(model=FakeS3DModel(logits), categories=categories, preprocess=fake_preprocess)

    obs = adapter.recognize([], clip_frames=make_frames())

    assert obs.label == "kinetics:running"
    assert obs.mode == "REAL"
    assert obs.confidence > 0.9


def test_metrics_include_top5_and_component_identifier():
    logits = torch.arange(5, dtype=torch.float32).unsqueeze(0)
    categories = ["a", "b", "c", "d", "e"]
    adapter = S3DKineticsAdapter(model=FakeS3DModel(logits), categories=categories, preprocess=fake_preprocess)

    obs = adapter.recognize([], clip_frames=make_frames())

    assert obs.metrics["s3d_component"] == "s3d_kinetics400"
    top5 = obs.metrics["s3d_top5"]
    assert len(top5) == 5
    assert top5[0]["label"] == "e"  # highest logit
    scores = [entry["score"] for entry in top5]
    assert scores == sorted(scores, reverse=True)


def test_raises_on_insufficient_frames():
    adapter = S3DKineticsAdapter(
        model=FakeS3DModel(torch.zeros(1, 5)), categories=["a"] * 5, preprocess=fake_preprocess
    )
    with pytest.raises(ValueError):
        adapter.recognize([], clip_frames=make_frames(n=3))


def test_raises_when_no_clip_frames_provided():
    adapter = S3DKineticsAdapter(
        model=FakeS3DModel(torch.zeros(1, 5)), categories=["a"] * 5, preprocess=fake_preprocess
    )
    with pytest.raises(ValueError):
        adapter.recognize([], clip_frames=None)


def test_label_is_prefixed_so_it_can_never_collide_with_the_threat_vocabulary():
    # Adversarial: even if the raw Kinetics category name happens to match one of this
    # project's real threat-relevant labels, the "kinetics:" prefix must guarantee it
    # can never be mistaken for -- or accidentally scored as -- that label. This is the
    # concrete safety net behind Phase 2R's "never map a Kinetics label to a threat
    # category" rule.
    from app.threat.rule_based import BASE_SCORE_BY_ACTION

    logits = torch.zeros(1, 3)
    logits[0, 0] = 10.0
    categories = ["fighting_candidate", "b", "c"]  # deliberately colliding name
    adapter = S3DKineticsAdapter(model=FakeS3DModel(logits), categories=categories, preprocess=fake_preprocess)

    obs = adapter.recognize([], clip_frames=make_frames())

    assert obs.label == "kinetics:fighting_candidate"
    assert obs.label not in BASE_SCORE_BY_ACTION


def test_adapter_does_not_require_real_weights():
    fake = FakeS3DModel(torch.zeros(1, 5))
    adapter = S3DKineticsAdapter(model=fake, categories=["a"] * 5, preprocess=fake_preprocess)
    assert adapter._model is fake
