import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.action_recognition.base import ActionObservation, ActionRecognitionAdapter
from app.schemas import DetectionResult

# Tuning constants for the heuristic — documented here rather than magic numbers inline.
CLOSE_PROXIMITY_RATIO = 0.15  # centroid distance < 15% of frame diagonal ~= "close"
FAST_MOVEMENT_PX_PER_SEC = 80.0  # rough px/sec centroid speed threshold for "running"

# Duplicate-box dedup (Phase 2P) — see docs/phase2o-live-system-audit.md for the real
# incident this fixes: a single person filling most of the frame produced 3 overlapping
# YOLO "person" boxes that survived YOLO's own internal NMS (which only suppresses
# same-class boxes above ~0.7 plain IoU), and were then each counted as a separate
# person, triggering a false close_contact/MEDIUM alert. Measured containment ratios
# (intersection / smaller-box-area — see _overlap_ratio) for that real incident's 3
# boxes were 0.876, 0.939, and 0.990 — all comfortably above this threshold. The
# threshold is deliberately well below that range (wide margin) so it reliably catches
# that failure mode without being fragile to it. It is also comfortably above what two
# genuinely distinct people standing near each other produce (~0.2-0.4 in this
# heuristic's synthetic tests) — see tests/test_action_recognizer.py.
DUPLICATE_BOX_OVERLAP_THRESHOLD = 0.7


class DemoHeuristicActionRecognizer(ActionRecognitionAdapter):
    """NOT a trained action-recognition model. Computes real geometry (bounding-box
    centroid proximity and movement speed) from whatever the detection stage produced,
    then maps that to a small action vocabulary with a hand-written rule set. This is
    clearly labeled mode="DEMO" everywhere it surfaces — see docs/ai-pipeline.md Stage 2
    for what a real trained model would need (dataset + GPU + training)."""

    mode = "DEMO"

    def recognize(
        self,
        window: List[Tuple[datetime, List[DetectionResult]]],
        clip_frames: Optional[List[np.ndarray]] = None,
        frame_width: Optional[int] = None,
        frame_height: Optional[int] = None,
    ) -> ActionObservation:
        # clip_frames is unused here — this adapter only ever reasons over detection
        # boxes, never raw pixels. Accepting (and ignoring) it is a required, purely
        # mechanical compatibility change for Phase 2H's call site in pipeline.py,
        # which calls recognize() the same way regardless of which adapter is
        # configured — it is NOT a behavior change to this class. See
        # app/action_recognition/base.py for why the parameter exists.
        #
        # frame_width/frame_height (Phase 2X): the actual decoded camera frame's
        # dimensions, when known — see _proximity_and_speed()/_frame_diagonal_estimate()
        # below for why this matters and what happens when it's None (the pre-Phase-2X
        # fallback, unchanged).
        if not window:
            return ActionObservation(label="no_activity", confidence=0.5, mode="DEMO", metrics={})

        person_counts = [
            len(_deduplicate_boxes([d for d in dets if d.object == "person"]))
            for _, dets in window
        ]
        avg_persons = sum(person_counts) / len(person_counts)

        if avg_persons < 0.5:
            return ActionObservation(
                label="no_activity",
                confidence=0.6,
                mode="DEMO",
                metrics={"avg_person_count": avg_persons},
            )

        min_proximity_ratio, movement_speed = _proximity_and_speed(window, frame_width, frame_height)

        metrics = {
            "avg_person_count": avg_persons,
            "min_proximity_ratio": min_proximity_ratio if min_proximity_ratio is not None else 1.0,
            "movement_speed_px_s": movement_speed,
        }

        if avg_persons >= 2 and min_proximity_ratio is not None and min_proximity_ratio < CLOSE_PROXIMITY_RATIO:
            if movement_speed >= FAST_MOVEMENT_PX_PER_SEC:
                label, confidence = "fighting_candidate", 0.55
            else:
                label, confidence = "close_contact", 0.5
        elif avg_persons >= 2 and movement_speed >= FAST_MOVEMENT_PX_PER_SEC:
            label, confidence = "approaching", 0.5
        elif movement_speed >= FAST_MOVEMENT_PX_PER_SEC:
            label, confidence = "running", 0.5
        elif movement_speed >= FAST_MOVEMENT_PX_PER_SEC / 4:
            label, confidence = "walking", 0.55
        else:
            label, confidence = "standing", 0.55

        return ActionObservation(label=label, confidence=confidence, mode="DEMO", metrics=metrics)


def _box_area(box: List[float]) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _overlap_ratio(a: List[float], b: List[float]) -> float:
    """Intersection-over-smaller-box ("containment") ratio: how much of the smaller of
    the two boxes is covered by the larger one. Deliberately not plain IoU — IoU under-
    weights the case where one box is a tighter or looser crop of the same underlying
    object (e.g. one YOLO candidate box for a person includes more of an outstretched
    arm than another), which is exactly the pattern seen in the real duplicate-person
    incident this function exists to catch. Two boxes that don't overlap at all return
    0.0; two identical boxes return 1.0."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    smaller_area = min(_box_area(a), _box_area(b))
    return intersection / smaller_area if smaller_area > 0 else 0.0


def _deduplicate_boxes(
    detections: List[DetectionResult], overlap_threshold: float = DUPLICATE_BOX_OVERLAP_THRESHOLD
) -> List[DetectionResult]:
    """Collapses detections whose boxes overlap so heavily they almost certainly
    represent the same physical object seen more than once (duplicate/near-duplicate
    YOLO candidate boxes surviving for one subject), rather than genuinely distinct
    objects — see DUPLICATE_BOX_OVERLAP_THRESHOLD's comment for the incident and
    numbers behind this. Greedy, confidence-first (mirrors how NMS itself prioritizes,
    though this is a separate, stricter pass): the highest-confidence box is always
    kept; any remaining box overlapping an already-kept box above the threshold is
    dropped. Order-independent in outcome for a given set of boxes. Not person-specific
    — callers pass in whatever subset (e.g. already filtered to `object == "person"`)
    they want deduplicated."""
    if len(detections) <= 1:
        return list(detections)
    ordered = sorted(detections, key=lambda d: d.confidence, reverse=True)
    kept: List[DetectionResult] = []
    for det in ordered:
        if all(_overlap_ratio(det.bounding_box, k.bounding_box) <= overlap_threshold for k in kept):
            kept.append(det)
    return kept


def _centroid(box: List[float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def _proximity_and_speed(
    window: List[Tuple[datetime, List[DetectionResult]]],
    frame_width: Optional[int] = None,
    frame_height: Optional[int] = None,
) -> Tuple[float | None, float]:
    """Returns (min pairwise person-centroid distance / frame diagonal, avg centroid
    movement speed in px/sec across consecutive frames — a rough, unweighted proxy, not
    per-identity tracking).

    Phase 2X: the "frame diagonal" the distance is normalized against now uses the
    ACTUAL decoded camera frame's dimensions (`frame_width`/`frame_height`) when known,
    computed once via `math.hypot(frame_width, frame_height)` — real geometry, not an
    estimate. When unavailable (None — the pre-Phase-2X default, and every existing
    caller/test that doesn't pass them), falls back unchanged to
    `_frame_diagonal_estimate()` below, preserving prior behavior exactly for anyone who
    doesn't supply real dimensions. See docs/phase2x-proximity-geometry-fix.md for the
    evidence this fixes (two people on opposite sides of frame, both spanning most of
    its height, previously read as "close" because the old estimate derived the
    diagonal from the boxes' own spread rather than the real frame)."""
    real_diag = math.hypot(frame_width, frame_height) if frame_width and frame_height else None

    min_ratio: float | None = None
    speeds: List[float] = []
    prev_centroid: Tuple[float, float] | None = None
    prev_time: datetime | None = None

    for timestamp, detections in window:
        people = _deduplicate_boxes([d for d in detections if d.object == "person"])
        boxes = [d.bounding_box for d in people]

        if len(boxes) >= 2:
            diag = real_diag if real_diag is not None else _frame_diagonal_estimate(boxes)
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    dist = _distance(_centroid(boxes[i]), _centroid(boxes[j]))
                    ratio = dist / diag if diag else 1.0
                    if min_ratio is None or ratio < min_ratio:
                        min_ratio = ratio

        if boxes:
            centroid = _centroid(boxes[0])
            if prev_centroid is not None and prev_time is not None:
                dt = max((timestamp - prev_time).total_seconds(), 0.001)
                speeds.append(_distance(prev_centroid, centroid) / dt)
            prev_centroid = centroid
            prev_time = timestamp

    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
    return min_ratio, avg_speed


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _frame_diagonal_estimate(boxes: List[List[float]]) -> float:
    # FALLBACK ONLY (Phase 2X) — used only when the real frame_width/frame_height are
    # not available to _proximity_and_speed() (e.g. a caller/test that predates Phase
    # 2X). Approximates using the spread of all boxes seen; this is the ORIGINAL
    # pre-Phase-2X estimate, unchanged, kept solely for backward compatibility.
    # Known weakness this fallback still has (why Phase 2X's real-geometry path is
    # preferred whenever dimensions are known): two people can appear "close" merely
    # because both boxes span most of the frame height, inflating this estimate,
    # regardless of their actual horizontal separation.
    xs = [c for box in boxes for c in (box[0], box[2])]
    ys = [c for box in boxes for c in (box[1], box[3])]
    width = max(xs) - min(xs) if xs else 1.0
    height = max(ys) - min(ys) if ys else 1.0
    return math.hypot(max(width, 1.0), max(height, 1.0)) * 3  # heuristic scale factor
