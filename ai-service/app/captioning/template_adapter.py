from collections import Counter
from typing import List, Optional

import numpy as np

from app.action_recognition.base import ActionObservation
from app.captioning.base import CaptioningAdapter
from app.schemas import DetectionResult

_ACTION_PHRASES = {
    "no_activity": "No significant activity detected.",
    "standing": "{people} standing in view.",
    "walking": "{people} walking through the scene.",
    "running": "{people} moving quickly through the scene.",
    "approaching": "{people} approaching one another.",
    "close_contact": "{people} in close proximity to one another.",
    "fighting_candidate": "Aggressive movement and close physical contact detected between {people}.",
}


def build_structured_sentence(
    detections: List[DetectionResult], action: ActionObservation, include_object_list: bool = True
) -> str:
    """The structured, activity-centric sentence shared by both captioning adapters
    (Phase 2AB) — built ONLY from real detections + the real action label, no model
    call, effectively instant. This is the PRIMARY semantic signal for "AI Analysis";
    see BlipCaptioner.caption() for how BLIP's own text is demoted to a clearly-labeled
    supplementary clause rather than being allowed to override this.

    `include_object_list=False` omits the trailing "Also detected: ..." clause — used
    by callers (BlipCaptioner) that append their own separately-labeled grounded list
    instead, to avoid stating the same real object list twice in different wording."""
    counts = Counter(d.object for d in detections)

    # Phase 2P: prefer the action recognizer's own deduplicated person count
    # (avg_person_count, present whenever DemoHeuristicActionRecognizer produced
    # this observation) over a raw recount of "person" detections. Multiple
    # overlapping YOLO boxes for one person can otherwise make the caption claim
    # more people than the deduplicated count the threat score is actually based
    # on -- exactly the discrepancy traced in docs/phase2o-live-system-audit.md.
    # Falls back to the raw count when metrics doesn't have it (e.g. an observation
    # built without going through DemoHeuristicActionRecognizer).
    avg_person_count = action.metrics.get("avg_person_count")
    people = round(avg_person_count) if avg_person_count is not None else counts.get("person", 0)
    people_phrase = _people_phrase(people)

    template = _ACTION_PHRASES.get(action.label, "{people} observed in the scene.")
    sentence = template.format(people=people_phrase)

    if include_object_list:
        other_objects = [obj for obj in counts if obj != "person"]
        if other_objects:
            sentence += f" Also detected: {', '.join(sorted(other_objects))}."

    return sentence


class TemplateCaptioner(CaptioningAdapter):
    """NOT a vision-language model — composes a sentence from the object counts and the
    recognized action label using fixed templates. See docs/ai-pipeline.md Stage 3."""

    mode = "DEMO"

    def caption(
        self,
        detections: List[DetectionResult],
        action: ActionObservation,
        frame: Optional[np.ndarray] = None,
        camera_id: Optional[str] = None,
    ) -> str:
        # frame/camera_id (Phase 2R) are unused here -- this adapter only ever reasons
        # over detections + the action label, exactly as before. Accepting (and
        # ignoring) them is a required, purely mechanical compatibility change so
        # pipeline.py can call every CaptioningAdapter the same way regardless of which
        # is configured -- not a behavior change to this class. See app/captioning/base.py.
        return build_structured_sentence(detections, action)


def _people_phrase(count: int) -> str:
    if count == 0:
        return "No people"
    if count == 1:
        return "One person"
    if count == 2:
        return "Two people"
    return f"{count} people"
