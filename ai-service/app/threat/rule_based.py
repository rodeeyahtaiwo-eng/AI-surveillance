from typing import Optional, Tuple

from app.action_recognition.base import ActionObservation
from app.threat.base import ThreatAssessmentAdapter

# Transparent, hand-set weights — not learned from data. Documented here so the score is
# always explainable (see docs/ai-pipeline.md Stage 4). A trained temporal model could
# replace this class behind the same ThreatAssessmentAdapter interface later.
BASE_SCORE_BY_ACTION = {
    "no_activity": 0.0,
    "standing": 0.05,
    "walking": 0.08,
    "running": 0.25,
    "approaching": 0.30,
    "close_contact": 0.40,
    "fighting_candidate": 0.70,
}

CLOSE_PROXIMITY_RATIO = 0.15
PROXIMITY_BONUS = 0.10
FAST_MOVEMENT_PX_PER_SEC = 80.0
MOVEMENT_BONUS = 0.05
ESCALATION_BONUS_CAP = 0.15

# Knife evidence (Phase 2S, recalibrated Phase 2AB) — see docs/phase2s-threat-
# reasoning.md and docs/phase2ab-live-stabilization.md. A single "knife" COCO-class
# detection is NOT reliable enough on its own to be treated as CONFIRMED (Phase 2O/2P
# found the same general detector also produces "tie"/"scissors" on the same kind of
# footage) — but Phase 2AB's live testing found that giving it ZERO signal until
# persistence (K-of-window) is met made a knife feel invisible to the demo for several
# real seconds. Three tiers now exist, all still gated on a person genuinely being
# present in the same window (action.metrics "avg_person_count") — a knife with no
# person/context remains explicitly NOT scored (Phase 2O's own recommendation),
# unchanged this phase:
#   1. UNCONFIRMED single-window sighting ("knife_detected", NOT yet persisted) ->
#      a small, cautious floor -- elevated, but explicitly below the MEDIUM boundary
#      (0.4, backend/src/config/threatConfig.ts), so it cannot look like a confirmed
#      alert on the strength of one possibly-wrong frame.
#   2. CONFIRMED/persistent sighting ("knife_persisted" -- K=2 hits within the trailing
#      T=4s window, unchanged mechanism, see knife_persistence_min_hits/_window_seconds
#      in app/config.py and count_recent_frames_with_object_as_of() in
#      app/common/frame_buffer.py) -> floored to HIGH. A knife the detector has now
#      seen more than once, with a person in frame, is treated as a real armed-presence
#      signal, not "ordinary activity" -- this is the Phase 2AB policy change from
#      Phase 2S's original 0.45 (MEDIUM) floor for this same tier.
#   3. CONFIRMED sighting + the geometry heuristic ALREADY independently read
#      aggravating context (close_contact/fighting_candidate) in the same window ->
#      floored slightly higher again, still HIGH, not invented as CRITICAL -- multi-
#      signal corroboration can still reach CRITICAL only via the engine's existing,
#      unchanged proximity/movement/escalation bonuses stacking on top, exactly as
#      before this phase (see the worked arithmetic in docs/phase2ab-live-
#      stabilization.md). No tier here ever hard-codes CRITICAL.
# Every tier is a MAX/floor operation, never additive and never a reduction: it can
# only raise an already-computed score up to the relevant floor, never invent
# independently of the geometry heuristic's own reading and never lower it.
KNIFE_AGGRAVATING_LABELS = {"close_contact", "fighting_candidate"}
KNIFE_DETECTED_UNCONFIRMED_FLOOR = 0.35
KNIFE_WITH_PERSON_FLOOR = 0.65
KNIFE_WITH_AGGRESSIVE_CONTEXT_FLOOR = 0.70


class RuleBasedThreatEngine(ThreatAssessmentAdapter):
    """Weighted, fully transparent scoring — every point added to the score is
    traceable in the returned rationale string. This is "Temporal activity analysis and
    potential threat/escalation prediction": it reasons over the current window plus the
    trend from the previous window, never a single frame, and never claims certainty."""

    mode = "DEMO"  # built on demo-heuristic action recognition; see docs/ai-pipeline.md

    def assess(
        self, action: ActionObservation, previous_score: Optional[float]
    ) -> Tuple[float, str]:
        base = BASE_SCORE_BY_ACTION.get(action.label, 0.1)
        parts = [f"base risk for '{action.label}' = {base:.2f}"]
        score = base

        proximity = action.metrics.get("min_proximity_ratio")
        if proximity is not None and proximity < CLOSE_PROXIMITY_RATIO:
            score += PROXIMITY_BONUS
            parts.append(f"close physical proximity (+{PROXIMITY_BONUS:.2f})")

        speed = action.metrics.get("movement_speed_px_s", 0.0)
        if speed >= FAST_MOVEMENT_PX_PER_SEC:
            score += MOVEMENT_BONUS
            parts.append(f"fast movement (+{MOVEMENT_BONUS:.2f})")

        # Knife evidence floor (Phase 2S, recalibrated Phase 2AB) — see the constants'
        # comments above for the full three-tier reasoning. Inert (no-op) for any
        # ActionObservation that doesn't carry "knife_detected"/"knife_persisted"
        # metrics at all.
        knife_persisted = action.metrics.get("knife_persisted", 0.0) >= 1.0
        knife_detected = action.metrics.get("knife_detected", 0.0) >= 1.0
        person_present = action.metrics.get("avg_person_count", 0.0) >= 0.5

        if (knife_persisted or knife_detected) and not person_present:
            parts.append("knife detected but no corroborating person in this window (not scored as elevated)")
        elif knife_persisted and person_present:
            aggravated = action.label in KNIFE_AGGRAVATING_LABELS
            knife_floor = KNIFE_WITH_AGGRESSIVE_CONTEXT_FLOOR if aggravated else KNIFE_WITH_PERSON_FLOOR
            if knife_floor > score:
                label_note = f" + '{action.label}'" if aggravated else ""
                parts.append(f"knife detected (persisted) + person present{label_note} -> raised to {knife_floor:.2f}")
                score = knife_floor
            else:
                parts.append(f"knife detected (persisted) + person present (already >= {knife_floor:.2f})")
        elif knife_detected and person_present:
            # Not yet confirmed by persistence -- a smaller, explicitly cautious floor
            # (see KNIFE_DETECTED_UNCONFIRMED_FLOOR's comment above).
            if KNIFE_DETECTED_UNCONFIRMED_FLOOR > score:
                parts.append(
                    f"knife detected (unconfirmed, not yet persisted) + person present "
                    f"-> raised to {KNIFE_DETECTED_UNCONFIRMED_FLOOR:.2f} (cautious, not a confirmed alert)"
                )
                score = KNIFE_DETECTED_UNCONFIRMED_FLOOR
            else:
                parts.append(
                    f"knife detected (unconfirmed) + person present (already >= {KNIFE_DETECTED_UNCONFIRMED_FLOOR:.2f})"
                )

        if previous_score is not None and previous_score > 0.25 and score >= previous_score:
            bonus = min(ESCALATION_BONUS_CAP, (score - previous_score) * 0.5 + 0.05)
            score += bonus
            parts.append(f"sustained/rising activity across recent windows (+{bonus:.2f})")

        score = max(0.0, min(1.0, score))

        rationale = f"{' + '.join(parts)} = {score:.2f}."
        if score >= 0.65:
            rationale += " Potential escalation to physical violence."
        elif score >= 0.4:
            rationale += " Elevated activity warranting attention."

        return score, rationale
