from datetime import datetime
from typing import List

import httpx

from app.common.logger import get_logger
from app.config import settings
from app.schemas import ActionResult, DetectionResult

logger = get_logger(__name__)


def _headers() -> dict:
    return {"x-ingest-key": settings.ingest_api_key, "Content-Type": "application/json"}


async def send_detections(camera_id: str, mode: str, frame_timestamp: datetime, detections: List[DetectionResult]) -> None:
    """Forwards detection results to the backend's ingestion API (see
    backend/src/routes/inference.routes.ts). Failures are logged, not raised — a backend
    outage should not crash frame processing."""
    if not detections:
        return
    body = {
        "cameraId": camera_id,
        "mode": mode,
        "detections": [
            {
                "objectLabel": d.object,
                "confidence": d.confidence,
                "boundingBox": d.bounding_box,
                "frameTimestamp": frame_timestamp.isoformat(),
            }
            for d in detections
        ],
    }
    await _post("/api/inference/detections", body)


async def send_action(
    camera_id: str,
    action: ActionResult,
    window_start: datetime,
    window_end: datetime,
) -> None:
    body = {
        "cameraId": camera_id,
        "mode": action.mode,
        "label": action.label,
        "confidence": action.confidence,
        "description": action.description,
        "windowStart": window_start.isoformat(),
        "windowEnd": window_end.isoformat(),
        "threatScore": action.threat_score,
        "rationale": action.rationale,
    }
    await _post("/api/inference/actions", body)


async def _post(path: str, body: dict) -> None:
    url = f"{settings.backend_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(url, json=body, headers=_headers())
            if res.status_code >= 400:
                logger.warning(f"Backend rejected POST {path}: {res.status_code} {res.text}")
    except httpx.HTTPError as exc:
        logger.warning(f"Failed to reach backend at {url}: {exc}")
