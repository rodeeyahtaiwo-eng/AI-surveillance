"""Order-1 Markov transition model (Phase 2R) — the smallest viable temporal predictor
recommended by the Phase 2Q feasibility spike. Fully transparent (a literal, inspectable
frequency table per camera), consistent with this project's RuleBasedThreatEngine
philosophy of explainable-over-black-box.

VALIDATION, STATED EXACTLY (do not round up): Phase 2Q measured "71% walk-forward
next-label accuracy on the evaluated historical sequence, compared with 61% for a
repeat-current-label baseline; this is a prototype validation result and is not a
generalization estimate." That sequence was dominated by one camera's repeated scripted
demo behavior — see docs/phase2q-s3d-blip-temporal-feasibility.md and
docs/phase2r-integration.md. This adapter has NOT been separately re-validated; it
implements the same order-1 transition-counting approach that produced that result.

LIMITATION, STATED EXACTLY: this adapter's history is in-memory, per ai-service
process, per camera — it starts empty on every ai-service restart. It does NOT read
the backend's persisted Action history to bootstrap itself, to avoid adding a new
backend-read API in this phase (see docs/phase2r-integration.md). It genuinely learns
from live traffic within the process's uptime, but has zero knowledge of anything
before that."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.temporal_prediction.base import PredictedEvent, PredictionOutcome, TemporalPredictionAdapter

SOURCE = "temporal_markov_v1"


class MarkovTemporalPredictor(TemporalPredictionAdapter):
    # "REAL" here means genuine empirical frequency statistics computed from actual
    # observed transitions in this process — not a claim of forecasting accuracy, and
    # not a trained/learned model in the ML sense. See module docstring.
    mode = "REAL"

    def __init__(self, max_history: int = 50) -> None:
        self.max_history = max_history
        self._last_label: Dict[str, str] = {}
        self._history_length: Dict[str, int] = defaultdict(int)
        # camera_id -> from_label -> Counter[to_label]
        self._transitions: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        # camera_id -> (predicted_label, confidence) from the most recent predict_next()
        # call not yet resolved by an observe() call (Phase 2T) — see PredictionOutcome.
        self._pending_prediction: Dict[str, Tuple[Optional[str], float]] = {}

    def observe(self, camera_id: str, label: str, timestamp: datetime) -> Optional[PredictionOutcome]:
        outcome: Optional[PredictionOutcome] = None
        pending = self._pending_prediction.pop(camera_id, None)
        if pending is not None:
            predicted_label, predicted_confidence = pending
            outcome = PredictionOutcome(
                predicted_label=predicted_label,
                predicted_confidence=predicted_confidence,
                actual_label=label,
                matched=(predicted_label == label) if predicted_label is not None else None,
            )

        prev = self._last_label.get(camera_id)
        if prev is not None:
            counter = self._transitions[camera_id][prev]
            counter[label] += 1
            # Bound memory per (camera, from_label) pair — oldest-weighted transitions
            # are never individually evicted (this is a frequency count, not a raw
            # event log), but cap the total observations counted from any one label so
            # a camera that's been running for a very long time doesn't grow this
            # table unboundedly. Simple, deterministic: halve all counts once the total
            # for this from_label exceeds max_history * 4 (generous headroom).
            if sum(counter.values()) > self.max_history * 4:
                for k in list(counter.keys()):
                    counter[k] = max(1, counter[k] // 2)
        self._last_label[camera_id] = label
        self._history_length[camera_id] = min(self._history_length[camera_id] + 1, self.max_history * 4)
        return outcome

    def predict_next(self, camera_id: str) -> PredictedEvent:
        now = datetime.now(timezone.utc)
        history_length = self._history_length.get(camera_id, 0)
        current = self._last_label.get(camera_id)

        if current is None:
            event = PredictedEvent(
                predicted_label=None,
                confidence=0.0,
                based_on_label=None,
                history_length=history_length,
                source=SOURCE,
                generated_at=now,
                rationale="No prior observations for this camera yet (cold start).",
            )
            self._pending_prediction[camera_id] = (None, 0.0)
            return event

        counter = self._transitions.get(camera_id, {}).get(current)
        if not counter:
            event = PredictedEvent(
                predicted_label=None,
                confidence=0.0,
                based_on_label=current,
                history_length=history_length,
                source=SOURCE,
                generated_at=now,
                rationale=f"'{current}' has never been followed by anything yet for this camera "
                          f"({history_length} total observations so far) — insufficient history "
                          f"for this specific transition.",
            )
            self._pending_prediction[camera_id] = (None, 0.0)
            return event

        total = sum(counter.values())
        distribution = {label: count / total for label, count in counter.items()}
        predicted_label, count = counter.most_common(1)[0]
        confidence = count / total

        event = PredictedEvent(
            predicted_label=predicted_label,
            confidence=confidence,
            based_on_label=current,
            history_length=history_length,
            source=SOURCE,
            generated_at=now,
            rationale=(
                f"Empirical transition frequency: '{current}' was followed by "
                f"'{predicted_label}' in {count}/{total} observed cases for this camera "
                f"({history_length} total observations this process's uptime)."
            ),
            distribution=distribution,
        )
        # Stashed here (not in observe()) so the NEXT observe() call for this camera —
        # whenever it happens — can resolve this exact prediction against whatever
        # label actually gets observed then. See PredictionOutcome.
        self._pending_prediction[camera_id] = (predicted_label, confidence)
        return event
