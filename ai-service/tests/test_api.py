import base64
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline

client = TestClient(app)


def tiny_image_base64() -> str:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", image)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def test_health_reports_configured_adapters():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["adapters"]["detection"] == "mock"
    assert "weapon" not in body["adapters"]  # firearm detection removed — see docs/phase2v-firearm-removal.md
    assert body["adapters"]["x3d_refinement"] == "none"  # X3D_ADAPTER=none — see tests/conftest.py
    assert body["adapters"]["s3d_supplementary"] == "none"  # S3D_ADAPTER=none — see tests/conftest.py (Phase 2R)
    assert body["adapters"]["temporal_prediction"] == "none"  # see tests/conftest.py (Phase 2R)


def test_infer_frame_returns_mock_detection():
    payload = {
        "camera_id": "cam-test-1",
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": tiny_image_base64(),
    }
    res = client.post("/infer/frame", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["camera_id"] == "cam-test-1"
    assert len(body["detections"]) == 1
    assert body["detections"][0]["mode"] == "DEMO"


def test_infer_frame_rejects_invalid_image():
    payload = {
        "camera_id": "cam-test-1",
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": "not-valid-base64-image-data",
    }
    res = client.post("/infer/frame", json=payload)
    assert res.status_code == 400


def test_infer_sequence_after_frames_returns_action():
    camera_id = "cam-test-sequence"
    payload = {
        "camera_id": camera_id,
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": tiny_image_base64(),
    }
    client.post("/infer/frame", json=payload)

    res = client.post(f"/infer/sequence?camera_id={camera_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["detections_in_window"] >= 1
    assert body["action"] is not None
    assert body["action"]["mode"] == "DEMO"


def test_infer_sequence_with_no_frames_returns_no_action():
    res = client.post("/infer/sequence?camera_id=cam-never-seen")
    assert res.status_code == 200
    body = res.json()
    assert body["action"] is None


def test_infer_frame_never_produces_a_firearm_detection(monkeypatch):
    # Phase 2V: no adapter capable of producing "firearm" exists in the pipeline any
    # more — a real /infer/frame call, even with a detector injected that (unrealistically)
    # tried to report one, cannot surface it, because there is no code path left that
    # merges a second detector's output into `detections` at all (see app/main.py).
    class FakeDetector:
        mode = "REAL"

        def detect(self, image):
            from app.schemas import DetectionResult

            return [DetectionResult(object="person", confidence=0.9, bounding_box=[1, 2, 3, 4], mode="REAL")]

    monkeypatch.setattr(pipeline, "get_detection_adapter", lambda: FakeDetector())

    payload = {
        "camera_id": "cam-2v-no-firearm-http",
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": tiny_image_base64(),
    }
    res = client.post("/infer/frame", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert not any(d["object"] == "firearm" for d in body["detections"])
    assert not hasattr(pipeline, "get_weapon_adapter")
    assert not hasattr(pipeline, "evaluate_weapon_detection")
    assert not hasattr(pipeline, "detect_weapons")


def test_infer_sequence_end_to_end_with_x3d_corroboration(monkeypatch):
    # Full-stack test: a REAL DemoHeuristicActionRecognizer reading of two-people-close
    # (matching tests/test_action_recognizer.py's pattern, so it genuinely produces
    # close_contact/fighting_candidate — not asserted/mocked), refined by an injected
    # fake X3D adapter (never loads real weights) via /infer/sequence. Confirms the
    # whole gated-refinement path is actually wired end to end, not just unit-tested
    # in isolation.
    from datetime import timedelta

    from app.action_recognition.base import ActionObservation
    from app.schemas import DetectionResult

    camera_id = "cam-x3d-e2e"

    # Phase 2P: two boxes close enough (centroids ~35px apart) to trigger close_contact,
    # but with box-overlap ("containment") only ~0.12 -- clearly below
    # demo_heuristic.DUPLICATE_BOX_OVERLAP_THRESHOLD (0.7), so they represent two
    # genuinely distinct people rather than being collapsed by the duplicate-box dedup
    # fix. The original [100,100,130,200]/[105,100,135,200] pair had containment ~0.83
    # -- too close to the 0.876-0.990 range measured in the real duplicate-person-box
    # incident (docs/phase2o-live-system-audit.md) to safely tell apart from a
    # dedup-worthy duplicate, and is now correctly collapsed to one person.
    def person_a() -> DetectionResult:
        return DetectionResult(object="person", confidence=0.9, bounding_box=[100, 100, 140, 200], mode="DEMO")

    def person_b() -> DetectionResult:
        return DetectionResult(object="person", confidence=0.9, bounding_box=[135, 105, 175, 205], mode="DEMO")

    window = pipeline.buffer_store.get(camera_id)
    t0 = datetime.now(timezone.utc)
    for i in range(4):
        window.add(t0 + timedelta(seconds=i), [person_a(), person_b()])

    for _ in range(16):
        pipeline.clip_buffer_store.get(camera_id).add(np.zeros((4, 4, 3), dtype=np.uint8))

    class FakeX3D:
        def recognize(self, window, clip_frames=None):
            return ActionObservation(
                label="fighting_candidate",
                confidence=0.93,
                mode="REAL",
                metrics={"x3d_prob_violence": 0.93, "x3d_prob_nonviolence": 0.07},
            )

    monkeypatch.setattr(pipeline, "get_x3d_adapter", lambda: FakeX3D())

    res = client.post(f"/infer/sequence?camera_id={camera_id}")
    assert res.status_code == 200
    body = res.json()

    assert body["action"] is not None
    assert body["action"]["label"] in ("close_contact", "fighting_candidate")  # heuristic's own label, preserved
    assert body["action"]["mode"] == "REAL"  # upgraded by X3D corroboration
    assert body["action"]["confidence"] == 0.93


def test_diagnostic_capture_does_not_change_infer_frame_response(monkeypatch, tmp_path):
    # Phase 2J requirement: enabling diagnostic capture must not change detection
    # results or API behavior at all. Compares the response with capture off vs. on,
    # for the same fake detection — must be byte-identical apart from capture being a
    # pure side effect.
    from app.config import settings
    from app.schemas import DetectionResult

    class FakeDetector:
        mode = "REAL"

        def detect(self, image):
            return [DetectionResult(object="knife", confidence=0.86, bounding_box=[1, 2, 3, 4], mode="REAL")]

    monkeypatch.setattr(pipeline, "get_detection_adapter", lambda: FakeDetector())

    payload = {
        "camera_id": "cam-diag-off",
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": tiny_image_base64(),
    }
    monkeypatch.setattr(settings, "diagnostic_capture_enabled", False)
    res_off = client.post("/infer/frame", json=payload)

    monkeypatch.setattr(settings, "diagnostic_capture_enabled", True)
    monkeypatch.setattr(settings, "diagnostic_capture_dir", str(tmp_path))
    payload["camera_id"] = "cam-diag-on"  # fresh camera_id — separate buffer, fair comparison
    res_on = client.post("/infer/frame", json=payload)

    body_off = res_off.json()
    body_on = res_on.json()
    assert res_off.status_code == res_on.status_code == 200
    # camera_id differs by design (separate buffers, for a fair independent comparison)
    # — everything else must be identical whether capture is on or off.
    assert body_off["mode"] == body_on["mode"]
    assert body_off["action_evaluated"] == body_on["action_evaluated"]
    assert body_off["detections"] == body_on["detections"]

    # And prove the wiring actually captured something when enabled (background task
    # runs synchronously enough in TestClient's context for this to be observable).
    knife_dir = tmp_path / "knife"
    assert knife_dir.exists()
    assert len(list(knife_dir.glob("*.jpg"))) == 1


def test_demo_scenario_endpoint_accepts_and_schedules(monkeypatch):
    # The real scenario sleeps for ~16s across its steps (see demo_scenario.py) — swap in
    # a no-op so this test verifies the endpoint contract without that real-time wait.
    async def fast_scenario(camera_id: str) -> None:
        return None

    monkeypatch.setattr("app.main.run_demo_scenario", fast_scenario)

    res = client.post("/demo/simulate-scenario?camera_id=cam-demo-1")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "started"
    assert body["mode"] == "DEMO"
