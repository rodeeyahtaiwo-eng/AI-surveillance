"""Phase 2M — controlled evaluation with confirmed POSITIVE evidence, alongside
confirmed negatives. Does not modify the detector, threshold, or Phase 2K geometry
filter — measurement only.

Reads ai-service/datasets/firearm_evaluation_v1/manifest.json (each entry labeled
"positive" or "negative" at authoring time, per the project's existing
webcam_validation_v1/manifest.json convention — see docs/phase2m-*.md), runs the real,
unmodified models/firearm_yolov8n.pt against every listed image, and reports detection
results, threshold sweeps, geometry-filter effect, and confusion matrices/precision-
recall ONLY where the sample size justifies it.

Usage (from ai-service/, venv active):
    venv/Scripts/python scripts/evaluate_phase2m_firearm.py
Writes ai-service/datasets/phase2m_firearm_eval_results.json.
"""
import json
import os

import cv2
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
AI_SERVICE_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AI_SERVICE_ROOT)

MODEL_PATH = os.path.join(REPO_ROOT, "models", "firearm_yolov8n.pt")
DATASET_DIR = os.path.join(AI_SERVICE_ROOT, "datasets", "firearm_evaluation_v1")
MANIFEST_PATH = os.path.join(DATASET_DIR, "manifest.json")

FLOOR_CONF = 0.5  # current production floor (FIREARM_CONFIDENCE_THRESHOLD default)
GEOMETRY_RATIO = 0.9  # current production geometry filter (Phase 2K default)
THRESHOLDS_TO_TEST = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def best_gun_box(model, image):
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


def confusion_matrix(rows, predict_fn):
    tp = fn = fp = tn = 0
    for r in rows:
        predicted_positive = predict_fn(r)
        if r["label"] == "positive":
            if predicted_positive:
                tp += 1
            else:
                fn += 1
        else:
            if predicted_positive:
                fp += 1
            else:
                tn += 1
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn}


def precision_recall(cm):
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) > 0 else None
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) > 0 else None
    return precision, recall


def main():
    manifest = json.load(open(MANIFEST_PATH))
    print(f"Loaded manifest: {sum(1 for m in manifest if m['label']=='positive')} positive, "
          f"{sum(1 for m in manifest if m['label']=='negative')} negative entries.\n")

    print(f"Loading real firearm model from {MODEL_PATH} ...")
    model = YOLO(MODEL_PATH)

    rows = []
    for entry in manifest:
        path = os.path.join(DATASET_DIR, entry["file"])
        image = cv2.imread(path)
        if image is None:
            print(f"WARNING: could not read {path}, skipping")
            continue
        best = best_gun_box(model, image)
        rows.append({
            "image_id": entry["image_id"],
            "label": entry["label"],
            "confidence": best["confidence"] if best else None,
            "bbox": best["bbox"] if best else None,
            "area_ratio": best["area_ratio"] if best else None,
        })

    n_pos = sum(1 for r in rows if r["label"] == "positive")
    n_neg = sum(1 for r in rows if r["label"] == "negative")
    print(f"Evaluated {len(rows)} images ({n_pos} positive, {n_neg} negative).\n")

    print("=== Per-image results ===")
    for r in rows:
        c = f"{r['confidence']:.3f}" if r["confidence"] is not None else "—"
        a = f"{r['area_ratio']:.3f}" if r["area_ratio"] is not None else "—"
        print(f"  [{r['label']:>8}] {r['image_id']:<12} conf={c:>6} area_ratio={a:>6}")

    print(f"\n=== Detection rate at conf>=0.5 (no filter) ===")
    pos_detected = sum(1 for r in rows if r["label"] == "positive" and r["confidence"] is not None)
    neg_detected = sum(1 for r in rows if r["label"] == "negative" and r["confidence"] is not None)
    print(f"  Positives detected: {pos_detected}/{n_pos}")
    print(f"  Negatives (false positives): {neg_detected}/{n_neg}")

    results = {"n_positive": n_pos, "n_negative": n_neg, "rows": rows, "by_setting": []}

    def make_predictor(threshold, use_geometry):
        def predict(r):
            if r["confidence"] is None or r["confidence"] < threshold:
                return False
            if use_geometry and r["area_ratio"] is not None and r["area_ratio"] > GEOMETRY_RATIO:
                return False
            return True
        return predict

    print("\n=== Confidence threshold sweep (no geometry filter) ===")
    for t in THRESHOLDS_TO_TEST:
        cm = confusion_matrix(rows, make_predictor(t, use_geometry=False))
        p, r_ = precision_recall(cm)
        p_str = f"{p:.2f}" if p is not None else "n/a"
        r_str = f"{r_:.2f}" if r_ is not None else "n/a"
        print(f"  conf>={t:.2f}: TP={cm['tp']} FN={cm['fn']} FP={cm['fp']} TN={cm['tn']}  precision={p_str} recall={r_str}")
        results["by_setting"].append({"threshold": t, "geometry": False, "confusion_matrix": cm, "precision": p, "recall": r_})

    print("\n=== Geometry filter only (current production default) ===")
    cm = confusion_matrix(rows, make_predictor(FLOOR_CONF, use_geometry=True))
    p, r_ = precision_recall(cm)
    print(f"  TP={cm['tp']} FN={cm['fn']} FP={cm['fp']} TN={cm['tn']}  precision={p} recall={r_}")
    results["by_setting"].append({"threshold": FLOOR_CONF, "geometry": True, "confusion_matrix": cm, "precision": p, "recall": r_})

    print("\n=== Confidence threshold + geometry filter together ===")
    for t in THRESHOLDS_TO_TEST:
        cm = confusion_matrix(rows, make_predictor(t, use_geometry=True))
        p, r_ = precision_recall(cm)
        p_str = f"{p:.2f}" if p is not None else "n/a"
        r_str = f"{r_:.2f}" if r_ is not None else "n/a"
        print(f"  conf>={t:.2f} + geometry: TP={cm['tp']} FN={cm['fn']} FP={cm['fp']} TN={cm['tn']}  precision={p_str} recall={r_str}")
        results["by_setting"].append({"threshold": t, "geometry": True, "confusion_matrix": cm, "precision": p, "recall": r_})

    out_path = os.path.join(AI_SERVICE_ROOT, "datasets", "phase2m_firearm_eval_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
