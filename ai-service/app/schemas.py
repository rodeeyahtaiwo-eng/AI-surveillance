from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

InferenceMode = Literal["REAL", "DEMO"]


class DetectionResult(BaseModel):
    object: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: List[float] = Field(min_length=4, max_length=4)
    mode: InferenceMode


class FrameInferenceRequest(BaseModel):
    camera_id: str
    frame_timestamp: datetime
    image_base64: str
    """JPEG/PNG image, base64-encoded (no data: URI prefix)."""


class FrameInferenceResponse(BaseModel):
    camera_id: str
    detections: List[DetectionResult]
    mode: InferenceMode
    action_evaluated: bool
    """True if this frame triggered an action/threat evaluation for the camera's window."""


class ActionResult(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    description: Optional[str] = None
    mode: InferenceMode
    threat_score: float = Field(ge=0, le=1)
    rationale: Optional[str] = None
    # Phase 2R — supplementary, informational only. Neither field ever contributes to
    # threat_score above; both are None unless their adapter is explicitly enabled
    # (S3D_ADAPTER=s3d_kinetics400 / TEMPORAL_PREDICTION_ADAPTER=markov_v1). Kept as
    # loosely-typed dicts rather than new top-level fields so a raw model prediction
    # can never be mistaken for a scored, threat-relevant judgment — see
    # docs/phase2r-integration.md "Critical semantic rule".
    s3d_prediction: Optional[dict] = None
    """Raw torchvision S3D Kinetics-400 top-1 (+top-5) prediction, UNMAPPED to any
    threat vocabulary. e.g. {"label": "baby waking up", "confidence": 0.17, "top5": [...],
    "component": "s3d_kinetics400"}. This is not a violence/threat signal."""
    temporal_prediction: Optional[dict] = None
    """Order-1 Markov next-label prediction from this camera's own recent action
    history (this process's uptime only). e.g. {"predicted_label": "standing",
    "confidence": 0.71, "based_on_label": "walking", "history_length": 12,
    "source": "temporal_markov_v1"}."""


class SequenceInferenceResponse(BaseModel):
    camera_id: str
    detections_in_window: int
    action: Optional[ActionResult] = None


class HealthResponse(BaseModel):
    ok: bool
    service: str = "ai-service"
    adapters: dict
