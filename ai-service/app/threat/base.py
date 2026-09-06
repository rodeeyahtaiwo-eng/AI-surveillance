from abc import ABC, abstractmethod
from typing import Optional, Tuple

from app.action_recognition.base import ActionObservation


class ThreatAssessmentAdapter(ABC):
    """Stage 4 interface — the project's core research component. Looks at the
    recognized action + its geometric metrics (and, via `previous_score`, the trend
    across recent windows) and produces a 0.0-1.0 "potential threat/escalation" score
    plus a human-readable rationale. This is framed as "Temporal activity analysis and
    potential threat/escalation prediction" — never a claim of certainty about future
    events. See docs/ai-pipeline.md Stage 4."""

    mode: str

    @abstractmethod
    def assess(
        self, action: ActionObservation, previous_score: Optional[float]
    ) -> Tuple[float, str]:
        """Returns (threat_score 0.0-1.0, rationale)."""
        raise NotImplementedError
