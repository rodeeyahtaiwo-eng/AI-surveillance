import asyncio
from datetime import datetime, timezone

from app.common.logger import get_logger
from app.schemas import ActionResult
from app.services import backend_client

logger = get_logger(__name__)

# Mirrors the example escalation timeline from the project spec / docs/ai-pipeline.md:
# standing -> approaching -> aggressive movement -> physical contact -> potential fight.
# Every step is explicitly mode="DEMO" with a rationale saying so — see docs/demo.md's
# rule that simulated events are never presented as real security incidents.
SCENARIO_STEPS = [
    {
        "delay_seconds": 0,
        "label": "standing",
        "description": "Two people are standing near the entrance.",
        "threat_score": 0.05,
    },
    {
        "delay_seconds": 4,
        "label": "approaching",
        "description": "One person is approaching the other.",
        "threat_score": 0.30,
    },
    {
        "delay_seconds": 4,
        "label": "close_contact",
        "description": "Aggressive movement detected between the two people.",
        "threat_score": 0.55,
    },
    {
        "delay_seconds": 4,
        "label": "fighting_candidate",
        "description": "Physical contact detected between the two people.",
        "threat_score": 0.78,
    },
    {
        "delay_seconds": 4,
        "label": "fighting_candidate",
        "description": "Sustained aggressive contact — potential fight detected.",
        "threat_score": 0.90,
    },
]


async def run_demo_scenario(camera_id: str) -> None:
    """Plays out a scripted DEMO escalation timeline for one camera, posting each step
    to the backend as it would arrive from a real pipeline run. This is NOT derived from
    analyzing any video — it's a fixed script for demonstrating the alert/incident
    pipeline end-to-end when no trained models / real footage are available. See
    docs/demo.md."""
    logger.info(f"Starting demo scenario for camera {camera_id}")
    window_start = datetime.now(timezone.utc)

    for i, step in enumerate(SCENARIO_STEPS):
        await asyncio.sleep(step["delay_seconds"])
        window_end = datetime.now(timezone.utc)

        action = ActionResult(
            label=step["label"],
            confidence=0.6,
            description=step["description"],
            mode="DEMO",
            threat_score=step["threat_score"],
            rationale=(
                f"Scripted demo scenario step {i + 1}/{len(SCENARIO_STEPS)} "
                f"(not derived from real video analysis) — see docs/demo.md."
            ),
        )
        await backend_client.send_action(camera_id, action, window_start, window_end)
        window_start = window_end

    logger.info(f"Demo scenario complete for camera {camera_id}")
