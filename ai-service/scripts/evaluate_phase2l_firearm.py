"""Phase 2L — controlled evaluation of the existing, UNMODIFIED firearm detector.

Does not change the model, the adapter, the confidence threshold, or the Phase 2K
geometry filter — this only measures. Two independent confirmed-negative evidence sets
are evaluated (see docs/phase2l-firearm-detector-evaluation.md for the full report):

1. "Known false positives" (n=45): real webcam frames under
   ai-service/diagnostics/frames/firearm/ that PREVIOUSLY triggered a firearm detection
   (Phase 2K's evidence set). Visually confirmed, frame by frame, to contain no firearm.
   This set is useful for testing whether a candidate filter catches already-known
   problem cases, but is a biased/circular sample for estimating an overall
   false-positive RATE (it was selected because these frames already triggered).

2. "Unbiased sample" (n=205): 5 evenly-spaced frames from each of 41 real webcam clips
   recorded for the unrelated X3D violence-classifier work
   (datasets/webcam_normal, webcam_staged_aggressive, webcam_staged_v2,
   webcam_validation_v1) — calm and staged-aggressive footage of a person, none of it
   selected for or against firearm content, none of it containing a firearm (confirmed
   by its own recording purpose and manifests — see docs/phase2c through phase2i).
   Sampling frames from it gives a genuinely unbiased estimate of how often the
   unmodified firearm detector fires on ordinary footage.

NO confirmed firearm-PRESENT evidence is available in this repository or retrievable
from the model's public model card (checked live) — see the report for why this is a
hard limitation, not a gap this script tries to paper over.

Usage: run from ai-service/ with the venv active:
    venv/Scripts/python scripts/evaluate_phase2l_firearm.py
Writes ai-service/datasets/phase2l_firearm_eval_results.json.
"""
import glob
import json
import os

import cv2
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AI_SERVICE_ROOT)

MODEL_PATH = os.path.join(REPO_ROOT, "models", "firearm_yolov8n.pt")
CAPTURES_DIR = os.path.join(AI_SERVICE_ROOT, "diagnostics", "frames", "firearm")
DATASETS_DIR = os.path.join(AI_SERVICE_ROOT, "datasets")

FLOOR_CONF = 0.5  # current production floor (FIREARM_CONFIDENCE_THRESHOLD default)
GEOMETRY_RATIO = 0.9  # current production geometry filter (Phase 2K default)
UNBIASED_DIRS = ["webcam_normal", "webcam_staged_aggressive", "webcam_staged_v2", "webcam_validation_v1"]
FRAMES_PER_CLIP = 5

CONF_THRESHOLDS_TO_TEST = [0.50, 0.60, 0.65, 0.70, 0.80, 0.85, 0.90]


def best_gun_box(model, image):
    """Returns the highest-confidence 'Gun' detection in this frame (conf>=FLOOR_CONF),
    or None. Never modifies or retrains the model — a plain, unmodified predict() call."""
    h, w = image.shape[:2]
    results = model.predict(image, conf=FLOOR_CONF, verbose=False)
    best = None
    for result in results:
        for box in result.boxes:
            if result.names[int(box.cls[0])].lower() != "gun":
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            ratio = (max(0, x2 - x1) * max(0, y2 - y1)) / (h * w)
            if best is None or conf > best["confidence"]:
                best = {"confidence": conf, "bbox": [round(v, 1) for v in (x1, y1, x2, y2)], "area_ratio": round(ratio, 4)}
    return best


def evaluate_known_false_positives(model):
    rows = []
    for jpg in sorted(glob.glob(os.path.join(CAPTURES_DIR, "*.jpg"))):
        meta_path = jpg[:-4] + ".json"
        meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        if meta.get("adapter") != "YoloV8FirearmAdapter":
            continue  # skip test-fixture captures (FakeWeaponAdapter, etc.)
        image = cv2.imread(jpg)
        best = best_gun_box(model, image)
        rows.append({
            "file": os.path.basename(jpg),
            "firearm_present": False,
            "confidence": round(best["confidence"], 4) if best else None,
            "bbox": best["bbox"] if best else None,
            "area_ratio": best["area_ratio"] if best else None,
        })
    return rows


def evaluate_unbiased_sample(model):
    clips = []
    for d in UNBIASED_DIRS:
        clips += sorted(glob.glob(os.path.join(DATASETS_DIR, d, "*.mp4")))

    rows = []
    for clip in clips:
        cap = cv2.VideoCapture(clip)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if n <= 0:
            cap.release()
            continue
        indices = sorted(set(int(n * i / FRAMES_PER_CLIP) for i in range(FRAMES_PER_CLIP)))
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            best = best_gun_box(model, frame)
            rows.append({
                "clip": os.path.relpath(clip, DATASETS_DIR).replace("\\", "/"),
                "frame_index": idx,
                "firearm_present": False,
                "confidence": round(best["confidence"], 4) if best else None,
                "bbox": best["bbox"] if best else None,
                "area_ratio": best["area_ratio"] if best else None,
            })
        cap.release()
    return rows


def summarize(rows, n_total, label):
    detected = [r for r in rows if r["confidence"] is not None]
    print(f"\n=== {label}: {len(detected)}/{n_total} flagged as 'Gun' at conf>=0.5 (no filter) ===")
    for t in CONF_THRESHOLDS_TO_TEST:
        conf_only = [r for r in detected if r["confidence"] >= t]
        combined = [r for r in conf_only if r["area_ratio"] <= GEOMETRY_RATIO]
        print(f"  conf>={t:.2f}: {len(conf_only)}/{n_total} alone, {len(combined)}/{n_total} with geometry filter too")
    geom_only = [r for r in detected if r["area_ratio"] <= GEOMETRY_RATIO]
    print(f"  geometry filter only (current production default): {len(geom_only)}/{n_total}")
    return {
        "n_total": n_total,
        "n_flagged_no_filter": len(detected),
        "by_threshold": {
            str(t): {
                "conf_only": len([r for r in detected if r["confidence"] >= t]),
                "conf_plus_geometry": len([r for r in detected if r["confidence"] >= t and r["area_ratio"] <= GEOMETRY_RATIO]),
            }
            for t in CONF_THRESHOLDS_TO_TEST
        },
        "geometry_only": len(geom_only),
    }


def main():
    print(f"Loading real firearm model from {MODEL_PATH} ...")
    model = YOLO(MODEL_PATH)

    known_fp_rows = evaluate_known_false_positives(model)
    unbiased_rows = evaluate_unbiased_sample(model)

    known_summary = summarize(known_fp_rows, len(known_fp_rows), "Known false positives (n=45, biased/circular sample)")
    unbiased_summary = summarize(unbiased_rows, len(unbiased_rows), "Unbiased sample (n=205, 41 clips x 5 frames)")

    out = {
        "confirmed_positive_evidence": {
            "n_images_available_locally": 0,
            "note": (
                "One prior manual smoke test (confidence 0.83) used the model author's "
                "own published example image on HuggingFace. That image is not stored "
                "in this repository and is not retrievable from the model's current "
                "HuggingFace model card (only training-curve/confusion-matrix images "
                "are published there; verified by fetching the card during this "
                "phase). No bounding box or image file exists for it. Zero confirmed "
                "firearm-present images are available for this evaluation."
            ),
        },
        "known_false_positives": {"rows": known_fp_rows, "summary": known_summary},
        "unbiased_sample": {"rows": unbiased_rows, "summary": unbiased_summary},
    }
    out_path = os.path.join(DATASETS_DIR, "phase2l_firearm_eval_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
