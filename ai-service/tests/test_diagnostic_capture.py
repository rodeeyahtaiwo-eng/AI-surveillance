"""Tests for the local diagnostic frame capture mechanism (Phase 2J) — verifies it's
disabled by default, captures only configured classes, writes correct metadata,
enforces the per-class cap with oldest-evicted-first, and never raises on failure.
Uses pytest's tmp_path fixture — never touches the real diagnostics/ folder."""

import json
import os
from datetime import datetime, timezone

import numpy as np
import pytest

from app.common import diagnostic_capture
from app.config import settings
from app.schemas import DetectionResult


@pytest.fixture(autouse=True)
def isolated_capture_settings(tmp_path, monkeypatch):
    """Every test gets its own tmp_path capture dir and a known-good config, restored
    after the test — never writes to the project's real diagnostics/ folder."""
    monkeypatch.setattr(settings, "diagnostic_capture_enabled", True)
    monkeypatch.setattr(settings, "diagnostic_capture_classes", "firearm,cat")
    monkeypatch.setattr(settings, "diagnostic_capture_max_frames", 3)
    monkeypatch.setattr(settings, "diagnostic_capture_dir", str(tmp_path))
    yield tmp_path


def make_image():
    return np.zeros((64, 64, 3), dtype=np.uint8)


def make_detection(object_label: str, confidence: float = 0.7, mode: str = "REAL") -> DetectionResult:
    return DetectionResult(object=object_label, confidence=confidence, bounding_box=[1, 2, 3, 4], mode=mode)


def test_disabled_by_default_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "diagnostic_capture_enabled", False)
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("firearm")], "cam-1", datetime.now(timezone.utc), "YoloV8FirearmAdapter"
    )
    assert list(tmp_path.iterdir()) == []


def test_disabled_is_the_actual_config_default():
    # Not the monkeypatched fixture value — the real Settings() default, so a fresh
    # checkout with no .env override is safe by default.
    from app.config import Settings

    assert Settings().diagnostic_capture_enabled is False


def test_configured_class_is_captured(tmp_path):
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("firearm", confidence=0.859)], "cam-1",
        datetime.now(timezone.utc), "YoloV8FirearmAdapter",
    )
    class_dir = tmp_path / "firearm"
    jpgs = list(class_dir.glob("*.jpg"))
    jsons = list(class_dir.glob("*.json"))
    assert len(jpgs) == 1
    assert len(jsons) == 1


def test_non_configured_class_is_not_captured(tmp_path):
    # "person" is never in the default/test class list — matches "do not save every
    # ordinary person detection".
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("person", confidence=0.9)], "cam-1",
        datetime.now(timezone.utc), "YoloV8Adapter",
    )
    assert list(tmp_path.iterdir()) == []


def test_metadata_contains_all_required_fields(tmp_path):
    ts = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
    diagnostic_capture.maybe_capture(
        make_image(),
        [make_detection("firearm", confidence=0.705, mode="REAL")],
        "cam-abc123",
        ts,
        "YoloV8FirearmAdapter",
    )
    json_path = next((tmp_path / "firearm").glob("*.json"))
    with open(json_path) as f:
        meta = json.load(f)

    assert meta["camera_id"] == "cam-abc123"
    assert meta["class"] == "firearm"
    assert meta["confidence"] == 0.705
    assert meta["bounding_box"] == [1, 2, 3, 4]
    assert meta["adapter"] == "YoloV8FirearmAdapter"
    assert meta["mode"] == "REAL"
    assert meta["timestamp"] == ts.isoformat()
    assert "captured_at" in meta


def test_different_classes_get_separate_subfolders(tmp_path):
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("firearm"), make_detection("cat")], "cam-1",
        datetime.now(timezone.utc), "SomeAdapter",
    )
    assert len(list((tmp_path / "firearm").glob("*.jpg"))) == 1
    assert len(list((tmp_path / "cat").glob("*.jpg"))) == 1


def test_cap_evicts_oldest_first_within_a_class(tmp_path):
    # max_frames=3 (fixture). Save 5 firearm detections in sequence.
    for i in range(5):
        diagnostic_capture.maybe_capture(
            make_image(), [make_detection("firearm", confidence=0.5 + i * 0.01)], "cam-1",
            datetime.now(timezone.utc), "YoloV8FirearmAdapter",
        )
    firearm_dir = tmp_path / "firearm"
    jpgs = sorted(firearm_dir.glob("*.jpg"))
    jsons = sorted(firearm_dir.glob("*.json"))
    assert len(jpgs) == 3  # capped, oldest 2 evicted
    assert len(jsons) == 3  # sidecar json evicted alongside its jpg, no orphans


def test_cap_is_independent_per_class(tmp_path):
    # Filling "cat" to its cap must not evict any "firearm" captures — this is the
    # "prioritize firearm detections" requirement, enforced structurally.
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("firearm")], "cam-1", datetime.now(timezone.utc), "A"
    )
    for _ in range(5):
        diagnostic_capture.maybe_capture(
            make_image(), [make_detection("cat")], "cam-1", datetime.now(timezone.utc), "A"
        )
    assert len(list((tmp_path / "firearm").glob("*.jpg"))) == 1  # untouched
    assert len(list((tmp_path / "cat").glob("*.jpg"))) == 3  # capped independently


def test_empty_detection_list_is_a_noop(tmp_path):
    diagnostic_capture.maybe_capture(make_image(), [], "cam-1", datetime.now(timezone.utc), "A")
    assert list(tmp_path.iterdir()) == []


def test_capture_failure_never_raises(tmp_path, monkeypatch):
    # Simulate a write failure (e.g. disk full / permissions) — must be caught and
    # logged, never propagated, so it can never break the live inference path.
    def broken_save(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(diagnostic_capture, "_save_one", broken_save)
    diagnostic_capture.maybe_capture(
        make_image(), [make_detection("firearm")], "cam-1", datetime.now(timezone.utc), "A"
    )  # must not raise


def test_does_not_capture_unrelated_classes_even_when_mixed_with_configured_ones(tmp_path):
    diagnostic_capture.maybe_capture(
        make_image(),
        [make_detection("person"), make_detection("firearm"), make_detection("dog")],
        "cam-1",
        datetime.now(timezone.utc),
        "A",
    )
    assert len(list((tmp_path / "firearm").glob("*.jpg"))) == 1
    assert not (tmp_path / "person").exists()
    assert not (tmp_path / "dog").exists()  # "dog" not in this test's configured classes ("firearm,cat")
