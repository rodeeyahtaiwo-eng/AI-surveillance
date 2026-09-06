from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional, Tuple

from app.schemas import DetectionResult

Entry = Tuple[datetime, List[DetectionResult]]


class CameraWindow:
    """Rolling buffer of (timestamp, detections) for one camera, used by the action
    recognition / threat assessment stages — which look at a *sequence* of frames, not
    a single one. See docs/ai-pipeline.md Stage 2-4."""

    def __init__(self) -> None:
        self.entries: Deque[Entry] = deque()
        self.last_evaluated_at: Optional[datetime] = None
        self.last_threat_score: float = 0.0
        self.last_x3d_eval_at: Optional[datetime] = None
        self.last_s3d_eval_at: Optional[datetime] = None

    def add(self, timestamp: datetime, detections: List[DetectionResult]) -> None:
        self.entries.append((timestamp, detections))

    def prune(self, window_seconds: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        while self.entries and _as_utc(self.entries[0][0]) < cutoff:
            self.entries.popleft()

    def all_detections(self) -> List[DetectionResult]:
        return [d for _, dets in self.entries for d in dets]

    def count_recent_frames_with_object_as_of(
        self, object_label: str, window_seconds: int, reference_time: datetime
    ) -> int:
        """Counts how many buffered frames within the trailing `window_seconds` of
        `reference_time` contain at least one detection of `object_label` — one count
        per FRAME, not per raw detection (so two overlapping boxes of the same class in
        one frame count once). Used by knife threat evidence (Phase 2S) — see
        app/services/pipeline.py's evaluate_window().

        Measured relative to an explicit `reference_time` rather than always wall-clock
        "now": BLIP (when CAPTION_ADAPTER=blip) runs synchronously inside
        evaluate_window(), and — because video-processing (and this project's own
        live-test client) sends each frame only after receiving the previous response —
        a multi-second BLIP generation on one frame pushes the NEXT frame's own recorded
        timestamp out by that same amount. A persistence check measured against
        wall-clock "now" at CHECK time can then find buffered frames already "too old"
        relative to now, even though they are only ~2-3s apart from each other by their
        own timestamps — a real, measured effect (see docs/phase2s-threat-reasoning.md),
        not a hypothetical one. Passing `window_end()` (the latest buffered frame's own
        timestamp) as `reference_time` makes the check depend only on the data's own
        recorded timing, immune to request-latency variance from whichever adapter
        happens to be configured."""
        cutoff = _as_utc(reference_time) - timedelta(seconds=window_seconds)
        count = 0
        for timestamp, detections in self.entries:
            if _as_utc(timestamp) < cutoff:
                continue
            if any(d.object.lower() == object_label.lower() for d in detections):
                count += 1
        return count

    def window_start(self) -> Optional[datetime]:
        return self.entries[0][0] if self.entries else None

    def window_end(self) -> Optional[datetime]:
        return self.entries[-1][0] if self.entries else None

    def should_evaluate(self, window_seconds: int) -> bool:
        if not self.entries:
            return False
        if self.last_evaluated_at is None:
            return True
        elapsed = datetime.now(timezone.utc) - _as_utc(self.last_evaluated_at)
        return elapsed >= timedelta(seconds=window_seconds)

    def mark_evaluated(self, threat_score: float) -> None:
        self.last_evaluated_at = datetime.now(timezone.utc)
        self.last_threat_score = threat_score

    def should_evaluate_x3d(self, cooldown_seconds: int) -> bool:
        """Rate-limits X3D-S refinement calls per camera — Phase 2H. Separate from
        should_evaluate() (the cheap heuristic's own cadence): a sustained
        close_contact/fighting_candidate state must not re-run the ~200-400ms X3D-S
        model every sequence_window_seconds indefinitely while it persists."""
        if self.last_x3d_eval_at is None:
            return True
        elapsed = datetime.now(timezone.utc) - _as_utc(self.last_x3d_eval_at)
        return elapsed >= timedelta(seconds=cooldown_seconds)

    def mark_x3d_evaluated(self) -> None:
        self.last_x3d_eval_at = datetime.now(timezone.utc)

    def should_evaluate_s3d(self, cooldown_seconds: int) -> bool:
        """Rate-limits S3D Kinetics-400 calls per camera (Phase 2R) — mirrors
        should_evaluate_x3d() exactly, as its own independent cooldown: S3D and X3D-S
        are two separate, independently-enabled supplementary signals and must not
        share rate-limit state."""
        if self.last_s3d_eval_at is None:
            return True
        elapsed = datetime.now(timezone.utc) - _as_utc(self.last_s3d_eval_at)
        return elapsed >= timedelta(seconds=cooldown_seconds)

    def mark_s3d_evaluated(self) -> None:
        self.last_s3d_eval_at = datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class FrameBufferStore:
    """Per-camera CameraWindow registry — one process-wide instance, see app/main.py."""

    def __init__(self) -> None:
        self._windows: Dict[str, CameraWindow] = {}

    def get(self, camera_id: str) -> CameraWindow:
        if camera_id not in self._windows:
            self._windows[camera_id] = CameraWindow()
        return self._windows[camera_id]
