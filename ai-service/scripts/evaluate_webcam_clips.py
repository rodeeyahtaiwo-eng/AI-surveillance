"""Phase 2E — run the existing Phase 2C classifier (frozen X3D-S + logistic-regression
head, unmodified) on the 8 newly-recorded webcam clips as an independent sanity check.

This is deliberately NOT a retrain and NOT an accuracy evaluation: these 8 clips were
never part of the training set, validation set, or feature cache used to fit the
classifier (see docs/phase2c-training.md), and this script does not add them there —
it writes its own, separately-named output artifact
(datasets/webcam_clips_eval.json) and leaves datasets/x3d_features.npz, split.json,
violence_head.json, and violence_head_metrics.json untouched.

Reuses the exact feature-extraction path from Phase 2C (scripts/x3d_common.py) and the
exact saved classifier weights (datasets/violence_head.json) — same math sklearn's
LogisticRegression.predict_proba would produce for a binary classifier, applied by hand
here to avoid an extra sklearn model-reconstruction step for what's a straightforward
sigmoid(coef . x + intercept).

Usage:
    venv\\Scripts\\python.exe scripts\\evaluate_webcam_clips.py
"""

import json
import math
import os

import numpy as np

from x3d_common import FeatureExtractor, clip_tensor_from_video, load_frozen_model

HEAD_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "violence_head.json")
DEFAULT_WEBCAM_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_normal")
DEFAULT_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_clips_eval.json")

CLASS_NAMES = {0: "NonViolence", 1: "Violence"}


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def predict(features: np.ndarray, coef: np.ndarray, intercept: float) -> tuple[int, float]:
    """Replicates sklearn LogisticRegression.predict/predict_proba for the binary case
    exactly: z = x.coef + intercept; P(class=1) = sigmoid(z)."""
    z = float(np.dot(features, coef) + intercept)
    prob_violence = sigmoid(z)
    predicted_class = 1 if prob_violence >= 0.5 else 0
    return predicted_class, prob_violence


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=DEFAULT_WEBCAM_DIR, help="Folder of .mp4 clips to evaluate")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Where to write the results JSON")
    args = parser.parse_args()
    webcam_dir = args.dir
    output_path = args.output

    with open(HEAD_PATH) as f:
        head = json.load(f)
    coef = np.array(head["coef"][0])  # (2048,) — binary LR stores one row
    intercept = float(head["intercept"][0])
    print(f"Loaded classifier head: {head['type']}, feature_dim={head['feature_dim']}, "
          f"classes={head['classes']} ({head['note']})")
    print("This is the EXACT Phase 2C classifier, unmodified — no retraining happened here.\n")

    print("Loading frozen X3D-S backbone (same as Phase 2C, not re-fit)...")
    model = load_frozen_model()
    extractor = FeatureExtractor(model)

    clip_files = sorted(f for f in os.listdir(webcam_dir) if f.endswith(".mp4"))
    print(f"\n{len(clip_files)} webcam clips to evaluate.\n")

    results = []
    for fn in clip_files:
        path = os.path.join(webcam_dir, fn)
        row = {"file": fn, "decode_ok": False, "feature_extraction_ok": False,
               "predicted_class": None, "prob_violence": None}
        try:
            clip = clip_tensor_from_video(path)
            row["decode_ok"] = True
        except Exception as exc:
            row["error"] = f"decode failed: {exc}"
            results.append(row)
            print(f"{fn}: DECODE FAILED — {exc}")
            continue

        try:
            features = extractor.extract(clip)
            row["feature_extraction_ok"] = True
        except Exception as exc:
            row["error"] = f"feature extraction failed: {exc}"
            results.append(row)
            print(f"{fn}: decode OK, FEATURE EXTRACTION FAILED — {exc}")
            continue

        predicted_class, prob_violence = predict(features, coef, intercept)
        row["predicted_class"] = CLASS_NAMES[predicted_class]
        row["prob_violence"] = round(prob_violence, 4)
        row["prob_nonviolence"] = round(1 - prob_violence, 4)
        results.append(row)
        print(f"{fn}: decode=OK  features=OK  predicted={row['predicted_class']:<11}  "
              f"P(violence)={prob_violence:.4f}  P(non-violence)={1 - prob_violence:.4f}")

    with open(output_path, "w") as f:
        json.dump(
            {
                "note": (
                    "Independent sanity check ONLY — not an accuracy score. These 8 clips "
                    "were never in the training/validation set. See docs/phase2e-webcam-eval.md."
                ),
                "classifier_source": "datasets/violence_head.json (Phase 2C, unmodified)",
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\nSaved to {output_path}")

    ok = [r for r in results if r["feature_extraction_ok"]]
    n_nonviolence = sum(1 for r in ok if r["predicted_class"] == "NonViolence")
    n_violence = sum(1 for r in ok if r["predicted_class"] == "Violence")
    print(f"\nSummary: {len(ok)}/{len(results)} clips processed successfully. "
          f"Predicted NonViolence: {n_nonviolence}, Predicted Violence: {n_violence}.")
    print("These clips are all expected-NonViolence footage (see docs/phase2d-webcam-fix.md) — "
          "this is a sanity check against that expectation, not a formal accuracy measurement "
          "(n=8, single unscripted session, no held-out ground-truth labeling process).")


if __name__ == "__main__":
    main()
