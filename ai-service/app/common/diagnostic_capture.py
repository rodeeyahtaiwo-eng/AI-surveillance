"""Local diagnostic frame capture — Phase 2J.

Saves the source frame + metadata for detections matching a configured class list
(default: "knife" only, since Phase 2V — see docs/phase2v-firearm-removal.md) so false
positives can be visually reviewed before any threshold/model decision is made. This
mechanism itself is generic/class-agnostic — it is purely additive and purely a side
effect:

- It NEVER changes what a detector returns, what gets persisted to the backend, what
  gets broadcast over WebSocket, or what the API responds with. Callers pass it
  detections *after* they've already been computed and used for everything else.
- It NEVER touches the backend database or any backend API — files are written to
  local disk only, under diagnostic_capture_dir (default: ai-service/diagnostics/frames/,
  git-ignored). This is a local dev artifact, not a project data store.
- It is disabled by default (DIAGNOSTIC_CAPTURE_ENABLED=false) and every write is
  wrapped so a failure here can NEVER propagate into the live inference path — worst
  case, a capture silently fails and is logged as a warning; nothing else is affected.

Disk usage is bounded by a per-class cap (diagnostic_capture_max_frames): each
configured class gets its own subfolder with its own oldest-evicted-first cap, so a
burst of one class (e.g. "cat") can never crowd out or evict evidence of another (e.g.
"knife") — see docs/ai-pipeline.md "Diagnostic frame capture".
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import List

import cv2
import numpy as np

from app.common.logger import get_logger
from app.config import settings
from app.schemas import DetectionResult

logger = get_logger(__name__)


def _configured_classes() -> set:
    return {c.strip().lower() for c in settings.diagnostic_capture_classes.split(",") if c.strip()}


def _class_dir(object_label: str) -> str:
    return os.path.join(settings.diagnostic_capture_dir, object_label.lower())


def _evict_if_over_cap(class_dir: str) -> None:
    """Deletes the oldest capture(s) in this class's subfolder if it exceeds the
    configured cap. Filenames are timestamp-prefixed (see _save_one), so a plain sort
    is chronological — no filesystem mtime dependency needed."""
    jpgs = sorted(f for f in os.listdir(class_dir) if f.endswith(".jpg"))
    excess = len(jpgs) - settings.diagnostic_capture_max_frames
    for fn in jpgs[: max(excess, 0)]:
        base = fn[: -len(".jpg")]
        for ext in (".jpg", ".json"):
            path = os.path.join(class_dir, base + ext)
            if os.path.exists(path):
                os.remove(path)


def _save_one(
    image: np.ndarray,
    detection: DetectionResult,
    camera_id: str,
    frame_timestamp: datetime,
    adapter_name: str,
) -> None:
    class_dir = _class_dir(detection.object)
    os.makedirs(class_dir, exist_ok=True)

    ts_compact = frame_timestamp.strftime("%Y%m%dT%H%M%S%f")[:-3]  # ms precision
    conf_tag = f"{round(detection.confidence * 1000):04d}"
    basename = f"{ts_compact}_{conf_tag}_{uuid.uuid4().hex[:8]}"

    jpg_path = os.path.join(class_dir, basename + ".jpg")
    json_path = os.path.join(class_dir, basename + ".json")

    ok, buf = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("Failed to JPEG-encode diagnostic frame")
    with open(jpg_path, "wb") as f:
        f.write(buf.tobytes())

    metadata = {
        "timestamp": frame_timestamp.isoformat(),
        "camera_id": camera_id,
        "class": detection.object,
        "confidence": detection.confidence,
        "bounding_box": detection.bounding_box,
        "adapter": adapter_name,
        "mode": detection.mode,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)

    _evict_if_over_cap(class_dir)


def maybe_capture(
    image: np.ndarray,
    detections: List[DetectionResult],
    camera_id: str,
    frame_timestamp: datetime,
    adapter_name: str,
) -> None:
    """Saves one frame+metadata pair per detection whose class is in
    diagnostic_capture_classes. No-op (single boolean check, no I/O) if capture is
    disabled or the list is empty — near-zero cost on the hot path either way.
    Never raises: any failure is logged and swallowed so the live inference path is
    never affected by a diagnostic-capture problem (e.g. a full disk, a permissions
    issue).
    """
    if not settings.diagnostic_capture_enabled or not detections:
        return

    wanted = _configured_classes()
    for detection in detections:
        if detection.object.lower() not in wanted:
            continue
        try:
            _save_one(image, detection, camera_id, frame_timestamp, adapter_name)
        except Exception as exc:  # noqa: BLE001 — a capture failure must never break inference
            logger.warning(f"Diagnostic frame capture failed for class={detection.object}: {exc}")
