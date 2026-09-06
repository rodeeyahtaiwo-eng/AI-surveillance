"""Phase 2V — explicit regression tests proving firearm detection has been removed from
the active runtime, per the required acceptance-criteria tests (A-I). Tests C-H
(knife/person/activity/threat-engine/temporal-invariant remain intact) are proven by the
existing, UNTOUCHED test files for those areas (test_knife_threat_pipeline.py,
test_action_recognizer.py, test_threat_engine.py, test_temporal_reasoning_pipeline.py) —
this file focuses on what's new: proving absence, not re-proving what already has its
own coverage."""

import importlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline
from app.threat.rule_based import BASE_SCORE_BY_ACTION

client = TestClient(app)


# --- Test A: firearm model is not loaded at normal startup ---------------------------


def test_the_weapon_package_no_longer_exists():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.weapon")


def test_pipeline_has_no_weapon_adapter_machinery():
    # Importing app.services.pipeline (already done at module load, for every test in
    # this suite) must never construct or reference a firearm model -- confirmed by the
    # complete absence of the functions/globals that used to do so.
    assert not hasattr(pipeline, "get_weapon_adapter")
    assert not hasattr(pipeline, "_weapon_adapter")
    assert not hasattr(pipeline, "detect_weapons")
    assert not hasattr(pipeline, "evaluate_weapon_detection")
    assert not hasattr(pipeline, "_firearm_candidate_is_plausible")


def test_health_endpoint_no_longer_reports_a_weapon_adapter():
    res = client.get("/health")
    assert res.status_code == 200
    assert "weapon" not in res.json()["adapters"]


def test_config_has_no_firearm_settings():
    from app.config import settings

    for attr in (
        "weapon_adapter",
        "firearm_model_path",
        "firearm_confidence_threshold",
        "firearm_max_bbox_area_ratio",
        "weapon_alert_cooldown_seconds",
        "firearm_persistence_min_hits",
        "firearm_persistence_window_seconds",
    ):
        assert not hasattr(settings, attr), f"settings.{attr} should have been removed"


def test_frame_buffer_has_no_firearm_specific_methods():
    from app.common.frame_buffer import CameraWindow

    window = CameraWindow()
    for attr in ("should_alert_weapon", "mark_weapon_alert", "last_weapon_alert_at", "count_recent_frames_with_plausible_firearm"):
        assert not hasattr(window, attr), f"CameraWindow.{attr} should have been removed"
    # The knife-evidence method must still be fully present and unaffected.
    assert hasattr(window, "count_recent_frames_with_object_as_of")


# --- Test B / H: a normal inference request cannot invoke or surface firearm inference -


def test_a_normal_infer_frame_request_never_invokes_or_surfaces_firearm_detection(tmp_path):
    import base64

    import cv2
    import numpy as np

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", image)
    assert ok
    payload = {
        "camera_id": "cam-2v-normal-request",
        "frame_timestamp": "2026-01-01T00:00:00Z",
        "image_base64": base64.b64encode(buf.tobytes()).decode("utf-8"),
    }
    res = client.post("/infer/frame", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert not any(d["object"] == "firearm" for d in body["detections"])


# --- Test I: no firearm-labeled event can be generated downstream --------------------


def test_no_code_path_can_produce_a_weapon_detected_threat_event():
    # "weapon_detected" is no longer a recognized action label anywhere in the scoring
    # table -- nothing upstream can even ask for this score any more, and if something
    # somehow still passed this exact string, it would silently fall through to the
    # generic unknown-label default rather than being treated specially.
    assert "weapon_detected" not in BASE_SCORE_BY_ACTION


def test_no_object_detector_in_the_active_pipeline_can_emit_the_label_firearm():
    # The only two places a DetectionResult is ever constructed in production code are
    # the general YOLO adapter (COCO classes only -- no "firearm"/"gun") and the now-
    # deleted firearm adapter. Confirms the general adapter's own class vocabulary
    # cannot produce "firearm" even in principle.
    from app.detection.yolov8_adapter import COCO_CLASSES

    assert "firearm" not in COCO_CLASSES
    assert "gun" not in [c.lower() for c in COCO_CLASSES]
    assert "knife" in COCO_CLASSES  # and knife is still there, unaffected
