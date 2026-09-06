"""Phase 2I — evaluates the EXISTING frozen classifier (unmodified since Phase 2C;
checksum-verified before this runs) against all 24 clips in
datasets/webcam_validation_v1/manifest.json, in one pass, with no exclusions.

Reuses the exact prediction math from scripts/evaluate_webcam_clips.py (sigmoid(coef .
features + intercept)) and the exact feature-extraction path from
scripts/x3d_common.py — nothing about the classifier or preprocessing is touched here.

Per the Phase 2I protocol: every clip in the manifest is scored and counted, regardless
of motion magnitude, predicted class, or confidence. Nothing is excluded post hoc.

Usage:
    venv\\Scripts\\python.exe scripts\\evaluate_phase2i.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from evaluate_webcam_clips import HEAD_PATH, predict  # noqa: E402
from x3d_common import FeatureExtractor, clip_tensor_from_video, load_frozen_model  # noqa: E402

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_validation_v1", "manifest.json")
CLIPS_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_validation_v1")
RESULTS_PATH = os.path.join(CLIPS_DIR, "evaluation_results.json")

POSITIVE_CLASS = "staged_aggressive"  # maps to the classifier's "Violence" (label 1)
NEGATIVE_CLASS = "calm"  # maps to "NonViolence" (label 0)


def confusion_counts(results):
    tp = fp = tn = fn = 0
    for r in results:
        if r["recording_status"] != "ok" or not r.get("feature_extraction_ok"):
            continue
        actual_positive = r["intended_class"] == POSITIVE_CLASS
        predicted_positive = r["predicted_class"] == "Violence"
        if actual_positive and predicted_positive:
            tp += 1
        elif actual_positive and not predicted_positive:
            fn += 1
        elif not actual_positive and predicted_positive:
            fp += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def compute_metrics(results):
    tp, fp, tn, fn = confusion_counts(results)
    n = tp + fp + tn + fn
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round(accuracy, 4), "precision": round(precision, 4),
        "recall": round(recall, 4), "f1": round(f1, 4),
    }


def main() -> None:
    with open(HEAD_PATH) as f:
        head = json.load(f)
    print(f"Classifier head: {head['type']}, feature_dim={head['feature_dim']}, "
          f"classes={head['classes']} ({head['note']})")
    print("Frozen since Phase 2C — NOT retrained, NOT modified for this evaluation.\n")

    import numpy as np
    coef = np.array(head["coef"][0])
    intercept = float(head["intercept"][0])

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    print(f"{len(manifest)} clips in the Phase 2I manifest.\n")

    print("Loading frozen X3D-S backbone...")
    model = load_frozen_model()
    extractor = FeatureExtractor(model)
    print("Loaded.\n")

    results = []
    for entry in manifest:
        row = dict(entry)  # carries clip_id, session_id, intended_class, motion_magnitude, etc.
        row["decode_ok"] = False
        row["feature_extraction_ok"] = False
        row["predicted_class"] = None
        row["prob_violence"] = None

        if entry["recording_status"] != "ok":
            row["error"] = "recording failed — excluded from metrics, reported separately"
            results.append(row)
            print(f"{entry['clip_id']}: RECORDING FAILURE (not decoded/evaluated)")
            continue

        path = os.path.join(CLIPS_DIR, entry["file"])
        try:
            clip = clip_tensor_from_video(path)
            row["decode_ok"] = True
        except Exception as exc:
            row["error"] = f"decode failed: {exc}"
            results.append(row)
            print(f"{entry['clip_id']}: DECODE FAILED — {exc}")
            continue

        try:
            features = extractor.extract(clip)
            row["feature_extraction_ok"] = True
        except Exception as exc:
            row["error"] = f"feature extraction failed: {exc}"
            results.append(row)
            print(f"{entry['clip_id']}: FEATURE EXTRACTION FAILED — {exc}")
            continue

        predicted_class, prob_violence = predict(features, coef, intercept)
        row["predicted_class"] = "Violence" if predicted_class == 1 else "NonViolence"
        row["prob_violence"] = round(prob_violence, 4)
        results.append(row)

        correct = (row["predicted_class"] == "Violence") == (entry["intended_class"] == POSITIVE_CLASS)
        print(f"{entry['clip_id']} (session {entry['session_id']}, intended={entry['intended_class']:<17} "
              f"motion={entry['motion_magnitude']:6.2f}): predicted={row['predicted_class']:<11} "
              f"P(violence)={prob_violence:.4f}  {'MATCH' if correct else 'MISMATCH'}")

    overall = compute_metrics(results)
    print(f"\n{'=' * 70}\nOVERALL (n={overall['n']})\n{'=' * 70}")
    print(f"Accuracy:  {overall['accuracy']}")
    print(f"Precision: {overall['precision']}  (of predicted staged-aggressive, how many were intended as such)")
    print(f"Recall:    {overall['recall']}  (of intended staged-aggressive, how many were caught)")
    print(f"F1:        {overall['f1']}")
    print(f"Confusion: TP={overall['tp']} FP={overall['fp']} TN={overall['tn']} FN={overall['fn']}")

    by_session = {}
    for session_id in sorted({e["session_id"] for e in manifest}):
        session_results = [r for r in results if r["session_id"] == session_id]
        by_session[session_id] = compute_metrics(session_results)
        m = by_session[session_id]
        print(f"\nSession {session_id} (n={m['n']}): accuracy={m['accuracy']} precision={m['precision']} "
              f"recall={m['recall']} f1={m['f1']} (TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']})")

    recording_failures = [r for r in results if r["recording_status"] != "ok"]
    decode_failures = [r for r in results if r["recording_status"] == "ok" and not r["decode_ok"]]
    extraction_failures = [
        r for r in results if r["recording_status"] == "ok" and r["decode_ok"] and not r["feature_extraction_ok"]
    ]
    print(f"\nRecording failures: {len(recording_failures)}  Decode failures: {len(decode_failures)}  "
          f"Feature-extraction failures: {len(extraction_failures)}")

    output = {
        "note": (
            "Phase 2I formal 24-clip deployment-domain validation. NOT combined with the "
            "historical 17 clips from Phases 2D-2G. See docs/phase2i-deployment-validation.md."
        ),
        "classifier_source": "models/violence_head.json (frozen since Phase 2C, unmodified)",
        "overall_metrics": overall,
        "metrics_by_session": by_session,
        "results": results,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
