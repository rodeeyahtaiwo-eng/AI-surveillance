import re
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

# Knife evidence (Phase 2S) — see docs/phase2s-threat-reasoning.md for the full
# investigation. A single "knife" COCO-class detection is NOT reliable enough on its
# own to score (Phase 2O/2P found the same general detector also produces "tie"/
# "scissors" on the same kind of footage) — this is a FLOOR, applied only once BOTH:
#   1. persistence confirms it (K-of-window, see knife_persistence_min_hits/
#      _window_seconds in app/config.py and count_recent_frames_with_object_as_of()
#      in app/common/frame_buffer.py) — not a one-frame blip, and
#   2. a person is genuinely present in the same window (action.metrics
#      "avg_person_count", computed by DemoHeuristicActionRecognizer using the
#      Phase 2P-deduplicated person count) — a knife with no person/context is
#      explicitly NOT scored as a threat (Phase 2O's own recommendation).
# It is a MAX/floor operation, never additive and never a reduction: it can only raise
# an already-computed score up to the relevant floor, never invent independently of the
# geometry heuristic's own reading and never lower it.
KNIFE_AGGRAVATING_LABELS = {"close_contact", "fighting_candidate"}
# Knife + person, no corroborating proximity/movement signal — worth an operator's
# attention (just above the MEDIUM floor) but not proof of an altercation.
KNIFE_WITH_PERSON_FLOOR = 0.45
# Knife + person + the geometry heuristic ALREADY independently read close proximity or
# fast movement in the same window — multi-signal corroboration, floored to HIGH
# (matching fighting_candidate's own base score exactly — not a fresh number, reusing
# an already-justified value). Deliberately NOT CRITICAL: no validated evidence exists
# that this combination confirms actual violence (see docs/phase2s-threat-reasoning.md).
KNIFE_WITH_AGGRESSIVE_CONTEXT_FLOOR = 0.70

# Phase 2AC — narrow, explicitly-labeled caption-based weapon-keyword corroboration.
# CONFIRMED GAP (see the current-state audit): the general YOLO detector has a real
# recall gap on certain knife presentations, while BLIP's raw caption text sometimes
# correctly names a weapon/violent act the structured detector entirely misses — a real
# recorded instance ("a woman holding a knife in her hand", three consecutive windows)
# scored 0.05-0.08 (LOW) because knife_persisted above never had a raw detection to
# work from. This is NOT a claim that BLIP's free-text understanding is validated —
# see app/captioning/blip_adapter.py's own hallucination warning (Phase 2Q: BLIP
# described a mirror that was not in the image). It is a deliberately modest,
# separately-logged FALLBACK signal for when the primary (grounded) detector comes up
# empty — never additive, applied only as a MAX/floor exactly like the KNIFE_* floors
# above, and gated on a person also being present in the window (same person-context
# policy as the knife floors). This logic is applied in app/services/pipeline.py, AFTER
# RuleBasedThreatEngine.assess() returns, deliberately kept OUT of assess() itself so
# the engine's own grounded-detection scoring path stays untouched and this fallback
# remains auditable and visually distinct (see the "[CAPTION-CORROBORATION: ...]"
# rationale tag and the dedicated logger.warning call) rather than silently blended
# into detection-based evidence.
CAPTION_WEAPON_KEYWORDS = ("knife", "gun", "weapon", "stabbing", "fighting")
# Deliberately BELOW KNIFE_WITH_PERSON_FLOOR (0.45) — a grounded-but-unpersisted
# detection is still stronger evidence than free-text caption content — and set exactly
# at the backend's MEDIUM severity threshold (backend/src/config/threatConfig.ts:
# MEDIUM >= 0.4): enough to surface the alert for operator attention when the primary
# detector's recall gap would otherwise leave it at LOW, without asserting the
# certainty a HIGH (0.65) or CRITICAL (0.85) alert implies from a single, lower-
# confidence, ungrounded text signal.
CAPTION_KEYWORD_FLOOR = 0.40


# Phase 2AH — persistence-gated escalation for REPEATED, independently-generated
# caption weapon-keyword matches — separate from CAPTION_KEYWORD_FLOOR above, which
# already fires on a single mention. Mirrors the KNIFE_* persistence pattern (multiple
# independent hits, not a one-frame/one-mention trust jump), applied to the caption
# signal instead of raw detections. See app/services/pipeline.py's
# CaptionKeywordHistoryStore for exactly how "distinct" hits are counted (consecutive
# identical caption text — plausible whenever BLIP's cooldown reuses one cached
# generation across several window evaluations — is deliberately NOT counted twice).
#
# Window sized against the REAL constraint, not the single-detection case's 4s: BLIP
# cannot produce a second independently-generated caption sooner than one full
# caption_blip_cooldown_seconds (20s) after the first, so a trailing window anywhere
# near the knife case's 4s (or even a naive "roughly double" 8-10s) could never
# observe two genuinely distinct generations at all — it would sit permanently
# unreachable. 45s comfortably exceeds 2x the 20s cooldown plus this project's own
# measured real inter-window cadence (~7-10s per evaluate_window() call in live
# testing), giving two real, independent BLIP generations room to both land inside the
# window without stretching so far that unrelated, long-separated mentions could
# combine into a false "persisted" reading.
CAPTION_KEYWORD_PERSISTENCE_MIN_HITS = 2
CAPTION_KEYWORD_PERSISTENCE_WINDOW_SECONDS = 45
# Reaches exactly the HIGH boundary (matching backend/src/config/threatConfig.ts:
# HIGH >= 0.65) — deliberately not pushed further into HIGH's own range or toward
# CRITICAL. Even reconfirmed across multiple independent generations, this remains an
# ungrounded, free-text signal, never a verified detection — repetition earns it a
# real escalation past CAPTION_KEYWORD_FLOOR's MEDIUM (0.40), but not the certainty a
# score deeper into HIGH or CRITICAL would imply.
CAPTION_KEYWORD_PERSISTED_FLOOR = 0.65


def contains_weapon_keyword(text: str) -> Optional[str]:
    """Returns the first CAPTION_WEAPON_KEYWORDS entry found in `text` (case-
    insensitive, whole-word match via \\b boundaries so e.g. "gunner" does not match
    "gun"), or None if none match. Deliberately a small fixed keyword list, not an
    attempt at general NLP/sentiment understanding."""
    if not text:
        return None
    lowered = text.lower()
    for keyword in CAPTION_WEAPON_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return keyword
    return None


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

        # Knife evidence floor (Phase 2S) — see the constants' comments above for the
        # full reasoning. Inert (no-op) for any ActionObservation that doesn't carry a
        # "knife_persisted" metric.
        knife_persisted = action.metrics.get("knife_persisted", 0.0) >= 1.0
        person_present = action.metrics.get("avg_person_count", 0.0) >= 0.5
        if knife_persisted and not person_present:
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
