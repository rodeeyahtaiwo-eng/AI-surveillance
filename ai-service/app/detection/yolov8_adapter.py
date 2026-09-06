from typing import List

import numpy as np

from app.common.logger import get_logger
from app.config import settings
from app.detection.base import ObjectDetectionAdapter
from app.schemas import DetectionResult

logger = get_logger(__name__)

# The 80 COCO classes YOLOv8n was pretrained on (from ultralytics' default weights).
# Documented here per the project rule "document supported classes" — see
# docs/ai-pipeline.md. Notably: NO firearm/gun class exists in COCO. "knife" IS a COCO
# class (dining-context images) — this is this project's only weapon-adjacent signal;
# firearm detection was evaluated and removed, see docs/phase2v-firearm-removal.md.
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]


class YoloV8Adapter(ObjectDetectionAdapter):
    """Real object detection: Ultralytics YOLOv8n, pretrained on COCO. CPU-capable.
    See COCO_CLASSES above for exactly what it can detect. Person/vehicle detection is
    solid; it is NOT a weapon detector (see docs/ai-pipeline.md)."""

    mode = "REAL"

    def __init__(self) -> None:
        # Imported lazily so importing this module (e.g. for type-checking or when
        # DETECTION_ADAPTER=mock is selected) doesn't require torch/ultralytics to be
        # installed or trigger a model download.
        from ultralytics import YOLO

        logger.info(f"Loading YOLOv8 model from {settings.yolo_model_path} ...")
        self.model = YOLO(settings.yolo_model_path)
        self.confidence_threshold = settings.yolo_confidence_threshold
        logger.info("YOLOv8 model loaded.")

    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        results = self.model.predict(image, conf=self.confidence_threshold, verbose=False)
        detections: List[DetectionResult] = []
        for result in results:
            for box in result.boxes:
                label = result.names[int(box.cls[0])]
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                detections.append(
                    DetectionResult(
                        object=label,
                        confidence=confidence,
                        bounding_box=[x1, y1, x2, y2],
                        mode="REAL",
                    )
                )
        return detections
