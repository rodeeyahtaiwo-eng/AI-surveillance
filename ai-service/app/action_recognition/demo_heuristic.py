import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.action_recognition.base import ActionObservation, ActionRecognitionAdapter
from app.schemas import DetectionResult

# Tuning constants for the heuristic — documented here rather than magic numbers inline.
CLOSE_PROXIMITY_RATIO = 0.15  # centroid distance < 15% of frame diagonal ~= "close"
FAST_MOVEMENT_PX_PER_SEC = 80.0  # rough px/sec centroid speed threshold for "running"

# Phase 2AC — minimal cross-frame identity matching for movement_speed. CONFIRMED BUG
# (see the current-state audit): the previous implementation compared boxes[0] (the
# highest-CONFIDENCE person box each frame, from _deduplicate_boxes) across consecutive
# frames as if it were one tracked person. When confidence ranking flips between two
# DISTINCT people frame-to-frame (empirically: two people posing for a selfie), this
# computed the distance between two different people's centroids and reported it as
# "speed" — the confirmed real cause of a false-positive fighting_candidate/CRITICAL
# alert on a benign selfie-taking pair. This is NOT full re-identification/tracking
# (out of scope) — just greedy nearest-centroid matching between one frame and the
# next, rejecting any match farther apart than MAX_MATCH_DISTANCE_RATIO of that frame's
# own diagonal estimate. Unmatched centroids (a person entering/leaving frame) simply
# contribute no speed sample for that frame pair, rather than being forced into a
# spurious match — under-counting speed is preferable to fabricating a cross-person
# jump as movement.
MAX_MATCH_DISTANCE_RATIO = 0.5

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
    ) -> ActionObservation:
        # clip_frames is unused here — this adapter only ever reasons over detection
        # boxes, never raw pixels. Accepting (and ignoring) it is a required, purely
        # mechanical compatibility change for Phase 2H's call site in pipeline.py,
        # which calls recognize() the same way regardless of which adapter is
        # configured — it is NOT a behavior change to this class. See
        # app/action_recognition/base.py for why the parameter exists.
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

        min_proximity_ratio, movement_speed = _proximity_and_speed(window)

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


def _match_centroids(
    prev_centroids: List[Tuple[float, float]],
    curr_centroids: List[Tuple[float, float]],
    max_distance: float,
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Greedy nearest-centroid matching between one frame's person centroids and the
    next's (Phase 2AC) — see MAX_MATCH_DISTANCE_RATIO's comment above for why this
    exists. For each current centroid (in order), matches it to whichever *unused*
    previous centroid is closest, but only accepts the match if that distance is within
    `max_distance`. Deliberately simple/greedy, not an optimal (e.g. Hungarian)
    assignment — sufficient to stop confidence-ranking flips from being read as
    movement, without introducing full tracking."""
    pairs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    remaining_prev = list(prev_centroids)
    for curr in curr_centroids:
        if not remaining_prev:
            break
        nearest = min(remaining_prev, key=lambda p: _distance(p, curr))
        # The distance veto only guards against genuine ambiguity -- i.e. a confidence-
        # ranking flip picking the WRONG one of several candidates (the confirmed bug).
        # When only one previous centroid remains, it is the only possible
        # correspondence regardless of distance: a single fast-moving subject covering
        # real ground between frames is not an identity-confusion case and must not be
        # discarded as "no match" (confirmed by test_fast_moving_single_person_is_running).
        if len(remaining_prev) == 1 or _distance(nearest, curr) <= max_distance:
            pairs.append((nearest, curr))
            remaining_prev.remove(nearest)
    return pairs


def _proximity_and_speed(
    window: List[Tuple[datetime, List[DetectionResult]]]
) -> Tuple[float | None, float]:
    """Returns (min pairwise person-centroid distance / frame diagonal, avg centroid
    movement speed in px/sec across consecutive frames). Speed is computed per matched
    identity via greedy nearest-centroid matching (Phase 2AC, see _match_centroids) —
    still not real re-identification/tracking, but no longer compares confidence-ranked
    array positions across frames as if they were the same person."""
    min_ratio: float | None = None
    speeds: List[float] = []
    prev_centroids: List[Tuple[float, float]] = []
    prev_time: datetime | None = None

    for timestamp, detections in window:
        people = _deduplicate_boxes([d for d in detections if d.object == "person"])
        boxes = [d.bounding_box for d in people]

        if len(boxes) >= 2:
            diag = _frame_diagonal_estimate(boxes)
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    dist = _distance(_centroid(boxes[i]), _centroid(boxes[j]))
                    ratio = dist / diag if diag else 1.0
                    if min_ratio is None or ratio < min_ratio:
                        min_ratio = ratio

        curr_centroids = [_centroid(box) for box in boxes]

        if curr_centroids and prev_centroids and prev_time is not None:
            dt = max((timestamp - prev_time).total_seconds(), 0.001)
            max_distance = _frame_diagonal_estimate(boxes) * MAX_MATCH_DISTANCE_RATIO
            for prev_centroid, curr_centroid in _match_centroids(prev_centroids, curr_centroids, max_distance):
                speeds.append(_distance(prev_centroid, curr_centroid) / dt)

        if curr_centroids:
            prev_centroids = curr_centroids
            prev_time = timestamp

    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
    return min_ratio, avg_speed


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _frame_diagonal_estimate(boxes: List[List[float]]) -> float:
    # No frame dimensions available here — approximate using the spread of all boxes
    # seen, which is good enough for a relative "close vs. far" ratio.
    xs = [c for box in boxes for c in (box[0], box[2])]
    ys = [c for box in boxes for c in (box[1], box[3])]
    width = max(xs) - min(xs) if xs else 1.0
    height = max(ys) - min(ys) if ys else 1.0
    return math.hypot(max(width, 1.0), max(height, 1.0)) * 3  # heuristic scale factor
