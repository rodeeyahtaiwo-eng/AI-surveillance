import base64
import logging
import time
from datetime import datetime, timezone

import cv2
import numpy as np
import requests

from src.config import AI_SERVICE_URL, SAMPLE_FPS
from src.sources.base import FrameSource

logger = logging.getLogger("video-processing")


def encode_frame(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to JPEG-encode frame")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def send_frame(camera_id: str, frame: np.ndarray) -> dict:
    """POSTs one sampled frame to ai-service. Raw frames are never sent through the
    normal backend REST API — only to ai-service, and only at SAMPLE_FPS, not every
    frame — see docs/architecture.md "Real-time processing"."""
    body = {
        "camera_id": camera_id,
        "frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_base64": encode_frame(frame),
    }
    response = requests.post(f"{AI_SERVICE_URL}/infer/frame", json=body, timeout=10)
    response.raise_for_status()
    return response.json()


def run(camera_id: str, source: FrameSource, max_frames: int | None = None) -> None:
    """Reads frames from `source` at SAMPLE_FPS and forwards each to ai-service. Runs
    until the source is exhausted (file sources loop unless configured not to) or
    interrupted, or until max_frames is reached (used by tests / short demo runs)."""
    interval = 1.0 / SAMPLE_FPS if SAMPLE_FPS > 0 else 0
    logger.info(
        f"Starting ingestion for camera_id={camera_id} source={source.label} "
        f"live={source.is_live} sample_fps={SAMPLE_FPS}"
    )

    frame_count = 0
    try:
        while True:
            frame = source.read()
            if frame is None:
                logger.info("Source exhausted — stopping.")
                break

            try:
                result = send_frame(camera_id, frame)
                logger.info(
                    f"frame {frame_count}: {len(result.get('detections', []))} detection(s)"
                    + (" — action window evaluated" if result.get("action_evaluated") else "")
                )
            except requests.RequestException as exc:
                logger.warning(f"Failed to reach ai-service: {exc}")

            frame_count += 1
            if max_frames is not None and frame_count >= max_frames:
                break
            if interval:
                time.sleep(interval)
    finally:
        source.release()
        logger.info(f"Stopped ingestion for camera_id={camera_id} after {frame_count} frame(s).")
