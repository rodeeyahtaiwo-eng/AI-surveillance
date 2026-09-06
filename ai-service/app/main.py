import asyncio
import base64

import cv2
import numpy as np
from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.common import diagnostic_capture
from app.common.logger import get_logger
from app.config import settings
from app.schemas import (
    FrameInferenceRequest,
    FrameInferenceResponse,
    HealthResponse,
    SequenceInferenceResponse,
)
from app.services import backend_client, pipeline
from app.services.demo_scenario import run_demo_scenario

logger = get_logger(__name__)

app = FastAPI(
    title="AI Surveillance — AI Service",
    description=(
        "Pluggable AI inference pipeline (object detection, action recognition, "
        "captioning, threat assessment). See docs/ai-pipeline.md for what's real vs. demo."
    ),
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        adapters={
            "detection": settings.detection_adapter,
            "action": settings.action_adapter,
            "x3d_refinement": settings.x3d_adapter,
            "caption": settings.caption_adapter,
            "threat": settings.threat_adapter,
            "s3d_supplementary": settings.s3d_adapter,
            "temporal_prediction": settings.temporal_prediction_adapter,
        },
    )


@app.post("/infer/frame", response_model=FrameInferenceResponse)
async def infer_frame(payload: FrameInferenceRequest, background_tasks: BackgroundTasks) -> FrameInferenceResponse:
    image = _decode_image(payload.image_base64)

    # Stage 1: general object detection (person/knife/vehicle/etc.) — unchanged. Firearm
    # detection (a separate model/adapter, Stage 1b) was removed in Phase 2V: the
    # evaluation evidence did not establish reliable firearm-vs-non-firearm
    # discrimination (see docs/phase2v-firearm-removal.md) — this is the only detector
    # in the active runtime now.
    detections = pipeline.detect_frame(image)
    mode = pipeline.get_detection_adapter().mode

    # Diagnostic frame capture (Phase 2J) — no-op unless DIAGNOSTIC_CAPTURE_ENABLED=true.
    # Purely a side effect: does not read from or modify `detections`/`mode`/the
    # response in any way. See app/common/diagnostic_capture.py.
    background_tasks.add_task(
        diagnostic_capture.maybe_capture,
        image, detections, payload.camera_id, payload.frame_timestamp,
        pipeline.get_detection_adapter().__class__.__name__,
    )

    window = pipeline.buffer_store.get(payload.camera_id)
    # Phase 2X: pass the real decoded frame's dimensions (image.shape is (height,
    # width, channels)) alongside detections, so proximity geometry can be normalized
    # against the actual frame — see CameraWindow.add() and demo_heuristic.py.
    frame_height, frame_width = image.shape[0], image.shape[1]
    window.add(payload.frame_timestamp, detections, frame_width=frame_width, frame_height=frame_height)
    window.prune(settings.sequence_window_seconds)

    # Raw-pixel buffer for X3D-S (Phase 2H) — populated unconditionally (a capped-deque
    # append is trivial cost) regardless of whether X3D_ADAPTER is enabled; only
    # actually read from if it is. See app/common/clip_buffer.py.
    pipeline.clip_buffer_store.get(payload.camera_id).add(image)

    background_tasks.add_task(
        backend_client.send_detections, payload.camera_id, mode, payload.frame_timestamp, detections
    )

    action_evaluated = False

    if window.should_evaluate(settings.sequence_window_seconds):
        # Run off the event loop: evaluate_window() can now include an X3D-S call
        # (Phase 2H, only when gated/enabled) costing ~200-400ms measured on this CPU
        # (docs/x3d-benchmark.md) — /infer/frame is hit every ~500ms by video-processing
        # and must not be stalled by it. Cheap when X3D never fires (the common case);
        # the thread-pool overhead itself is negligible either way.
        result = await asyncio.to_thread(pipeline.evaluate_window, payload.camera_id)
        if result:
            action_result, window_start, window_end = result
            background_tasks.add_task(
                backend_client.send_action, payload.camera_id, action_result, window_start, window_end
            )
            action_evaluated = True

    return FrameInferenceResponse(
        camera_id=payload.camera_id,
        detections=detections,
        mode=mode,  # type: ignore[arg-type]
        action_evaluated=action_evaluated,
    )


@app.post("/infer/sequence", response_model=SequenceInferenceResponse)
async def infer_sequence(camera_id: str, background_tasks: BackgroundTasks) -> SequenceInferenceResponse:
    """Manually triggers Stage 2-4 evaluation over whatever is currently buffered for
    this camera, instead of waiting for SEQUENCE_WINDOW_SECONDS to elapse. Useful for
    tests and for demo scripts that want tighter control over timing."""
    result = await asyncio.to_thread(pipeline.evaluate_window, camera_id)
    detections_in_window = len(pipeline.buffer_store.get(camera_id).all_detections())

    if not result:
        return SequenceInferenceResponse(camera_id=camera_id, detections_in_window=0, action=None)

    action_result, window_start, window_end = result
    background_tasks.add_task(backend_client.send_action, camera_id, action_result, window_start, window_end)

    return SequenceInferenceResponse(
        camera_id=camera_id, detections_in_window=detections_in_window, action=action_result
    )


@app.post("/demo/simulate-scenario")
async def simulate_scenario(camera_id: str, background_tasks: BackgroundTasks) -> dict:
    """Kicks off the scripted DEMO escalation timeline (docs/demo.md) for a camera. Runs
    in the background and posts each step to the backend as it happens."""
    background_tasks.add_task(run_demo_scenario, camera_id)
    return {"status": "started", "camera_id": camera_id, "mode": "DEMO"}


def _decode_image(image_base64: str) -> np.ndarray:
    try:
        raw = base64.b64decode(image_base64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:  # noqa: BLE001 — surface as a clean 400, not a 500
        raise HTTPException(status_code=400, detail=f"Invalid image data: {exc}") from exc
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image (unsupported format?)")
    return image
