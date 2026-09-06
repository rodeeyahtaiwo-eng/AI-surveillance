"""Unit tests for X3DViolenceAdapter using an injected fake feature extractor — never
loads the real X3D-S backbone or the real classifier head."""

import numpy as np
import pytest

from app.action_recognition.x3d_violence_adapter import NUM_FRAMES, X3DViolenceAdapter


class FakeExtractor:
    """Returns a canned feature vector regardless of input clip — tests control the
    classifier's effective input directly rather than needing a real backbone."""

    def __init__(self, features: np.ndarray):
        self._features = features
        self.last_clip_shape = None

    def extract(self, clip_tensor) -> np.ndarray:
        self.last_clip_shape = tuple(clip_tensor.shape)
        return self._features


def make_adapter(features: np.ndarray, coef: np.ndarray, intercept: float) -> X3DViolenceAdapter:
    return X3DViolenceAdapter(extractor=FakeExtractor(features), coef=coef, intercept=intercept)


def make_frames(n: int, h: int = 64, w: int = 64):
    return [np.zeros((h, w, 3), dtype=np.uint8) for _ in range(n)]


def test_high_violence_probability_yields_fighting_candidate():
    # A single-feature "classifier" for simplicity: coef=[10], intercept=0 — a positive
    # feature value drives z strongly positive, so sigmoid(z) -> ~1.
    adapter = make_adapter(features=np.array([1.0]), coef=np.array([10.0]), intercept=0.0)
    obs = adapter.recognize([], clip_frames=make_frames(NUM_FRAMES))

    assert obs.label == "fighting_candidate"
    assert obs.mode == "REAL"
    assert obs.confidence > 0.99
    assert obs.metrics["x3d_prob_violence"] > 0.99


def test_low_violence_probability_yields_no_activity():
    adapter = make_adapter(features=np.array([1.0]), coef=np.array([-10.0]), intercept=0.0)
    obs = adapter.recognize([], clip_frames=make_frames(NUM_FRAMES))

    assert obs.label == "no_activity"
    assert obs.mode == "REAL"
    assert obs.metrics["x3d_prob_violence"] < 0.01


def test_mode_is_always_real_when_it_runs_successfully():
    # mode="REAL" must reflect "genuine inference happened", not "violence confirmed" —
    # true for both the Violence and NonViolence outcomes.
    violence_adapter = make_adapter(np.array([1.0]), np.array([10.0]), 0.0)
    calm_adapter = make_adapter(np.array([1.0]), np.array([-10.0]), 0.0)

    violence_obs = violence_adapter.recognize([], clip_frames=make_frames(NUM_FRAMES))
    calm_obs = calm_adapter.recognize([], clip_frames=make_frames(NUM_FRAMES))

    assert violence_obs.mode == "REAL"
    assert calm_obs.mode == "REAL"


def test_metrics_include_both_probabilities_summing_to_one():
    adapter = make_adapter(np.array([0.5]), np.array([2.0]), -0.3)
    obs = adapter.recognize([], clip_frames=make_frames(NUM_FRAMES))
    total = obs.metrics["x3d_prob_violence"] + obs.metrics["x3d_prob_nonviolence"]
    assert abs(total - 1.0) < 1e-9


def test_raises_on_insufficient_frames_rather_than_guessing():
    adapter = make_adapter(np.array([1.0]), np.array([10.0]), 0.0)
    with pytest.raises(ValueError):
        adapter.recognize([], clip_frames=make_frames(NUM_FRAMES - 1))


def test_raises_on_no_frames():
    adapter = make_adapter(np.array([1.0]), np.array([10.0]), 0.0)
    with pytest.raises(ValueError):
        adapter.recognize([], clip_frames=None)


def test_uses_only_num_frames_uniformly_subsampled():
    # Feeds more frames than NUM_FRAMES needs — the adapter must subsample down to
    # exactly NUM_FRAMES before handing off to the extractor (matches
    # scripts/x3d_common.py's clip_tensor_from_video subsampling behavior).
    extractor = FakeExtractor(np.array([1.0]))
    adapter = X3DViolenceAdapter(extractor=extractor, coef=np.array([1.0]), intercept=0.0)
    adapter.recognize([], clip_frames=make_frames(40))
    # (1, C=3, T=NUM_FRAMES, H=182, W=182)
    assert extractor.last_clip_shape == (1, 3, NUM_FRAMES, 182, 182)


def test_does_not_require_real_weights():
    # Constructing with injected fakes must never touch torch.hub, the network, or the
    # filesystem. Reaching this line without an exception/network call IS the assertion.
    adapter = make_adapter(np.array([1.0]), np.array([1.0]), 0.0)
    assert adapter.mode == "REAL"
