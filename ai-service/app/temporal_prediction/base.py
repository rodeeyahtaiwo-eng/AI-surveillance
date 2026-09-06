"""Stage 4.5 interface (Phase 2R) — SUPPLEMENTARY to the threat engine, never an input
to it. Predicts the likely next action label for a camera from that camera's own recent
label history, using genuine temporal history (a sequence of past labels), not simply
the current label repeated. See app/temporal_prediction/markov_adapter.py for the first
implementation and docs/phase2r-integration.md for the validation evidence and its
explicit limits."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class PredictedEvent:
    """Output of the temporal prediction stage.

    `predicted_label=None` means "no prediction possible" (cold start, or this camera's
    current label has no recorded successor yet) — this adapter never fabricates a
    guess when it has no history to draw on. `confidence` is the empirical transition
    frequency (count of this transition / total transitions observed from the current
    label) — a real frequency statistic, not a claim of forecasting accuracy. See
    `rationale` for a human-readable explanation of exactly what evidence (and how much
    of it) produced this prediction."""

    predicted_label: Optional[str]
    confidence: float
    based_on_label: Optional[str]
    history_length: int
    source: str
    generated_at: datetime
    rationale: str
    distribution: Dict[str, float] = field(default_factory=dict)
    """Full normalized transition distribution from `based_on_label` (sums to 1.0 when
    non-empty) — not just the top prediction, so the confidence figure above is
    auditable against the complete picture, not asserted in isolation."""


@dataclass
class PredictionOutcome:
    """Result of comparing a PREVIOUSLY made prediction (from the last predict_next()
    call for this camera) against the label actually observed next (Phase 2T).

    This is the "prediction -> outcome validation" half of temporal reasoning: a
    prediction on its own is not evidence of anything until checked against what
    actually happened. `matched=None` means there was nothing to compare (no prior
    prediction existed — e.g. this is the camera's first-ever observation, or the
    prior prediction already had `predicted_label=None` because of insufficient
    history)."""

    predicted_label: Optional[str]
    predicted_confidence: Optional[float]
    actual_label: str
    matched: Optional[bool]


class TemporalPredictionAdapter(ABC):
    """Plug-in point for a temporal next-event predictor. `observe()` and
    `predict_next()` are deliberately separate calls (not one combined method) so a
    caller can predict from history strictly BEFORE recording the new observation —
    avoiding the current event leaking into its own prediction, matching the
    walk-forward validation methodology in docs/phase2q-s3d-blip-temporal-feasibility.md."""

    mode: str

    @abstractmethod
    def observe(self, camera_id: str, label: str, timestamp: datetime) -> Optional[PredictionOutcome]:
        """Records one real action-label observation for this camera, updating the
        model's internal transition statistics, and returns the outcome of comparing
        WHATEVER WAS PREDICTED at the last predict_next() call for this camera against
        `label` (the newly observed, actual label) — None if there was no pending
        prediction to resolve. Call this AFTER predict_next() for the same event, not
        before."""
        raise NotImplementedError

    @abstractmethod
    def predict_next(self, camera_id: str) -> PredictedEvent:
        """Predicts the next label for this camera from its history so far (not
        including any event not yet passed to observe()). Never raises — returns a
        PredictedEvent with predicted_label=None when there isn't enough history."""
        raise NotImplementedError
