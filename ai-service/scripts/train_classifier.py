"""Train and evaluate the lightweight violence/non-violence classification head —
Phase 2C, Steps 4/8.

Trains ONLY a small classifier on top of cached, frozen X3D-S features (see
extract_features.py) — the X3D-S backbone itself is never updated, per the approved
Phase 2C plan. This is a standalone training/evaluation artifact; it does not modify
app/action_recognition/* or wire into the live pipeline — see docs/phase2c-training.md
"Not yet integrated" for what a later integration phase would still need to do.

Reports accuracy, precision, recall, F1, and the confusion matrix — not accuracy alone,
per the approved plan (a domain-biased dataset makes accuracy-only reporting
particularly easy to over-trust).

Usage:
    venv\\Scripts\\python.exe scripts\\train_classifier.py
"""

import json
import os

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "x3d_features.npz")
SPLIT_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "split.json")
MODEL_OUT = os.path.join(os.path.dirname(__file__), "..", "datasets", "violence_head.json")
METRICS_OUT = os.path.join(os.path.dirname(__file__), "..", "datasets", "violence_head_metrics.json")


def main() -> None:
    data = np.load(FEATURES_PATH, allow_pickle=True)
    features, labels = data["features"], data["labels"]

    with open(SPLIT_PATH) as f:
        split = json.load(f)
    train_idx, val_idx = np.array(split["train_idx"]), np.array(split["val_idx"])

    X_train, y_train = features[train_idx], labels[train_idx]
    X_val, y_val = features[val_idx], labels[val_idx]

    print(f"Train: {len(X_train)} ({(y_train==1).sum()} Violence, {(y_train==0).sum()} NonViolence)")
    print(f"Val:   {len(X_val)} ({(y_val==1).sum()} Violence, {(y_val==0).sum()} NonViolence)")

    # class_weight="balanced" matters here specifically because filtering left a ~4:1
    # Violence:NonViolence imbalance (998 vs 250, see docs/phase2c-training.md) — without
    # it, a lightweight linear head would trivially learn to just predict the majority
    # class and still score high raw accuracy, which is exactly the kind of misleading
    # accuracy-only number this evaluation is designed to avoid.
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=2026)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_val)

    metrics = {
        "accuracy": accuracy_score(y_val, y_pred),
        "precision": precision_score(y_val, y_pred),
        "recall": recall_score(y_val, y_pred),
        "f1": f1_score(y_val, y_pred),
        "confusion_matrix": confusion_matrix(y_val, y_pred).tolist(),  # [[TN,FP],[FN,TP]]
        "n_train": len(X_train),
        "n_val": len(X_val),
        "train_class_balance": {"violence": int((y_train == 1).sum()), "nonviolence": int((y_train == 0).sum())},
        "val_class_balance": {"violence": int((y_val == 1).sum()), "nonviolence": int((y_val == 0).sum())},
    }

    print("\n=== Validation metrics ===")
    print(f"Accuracy:  {metrics['accuracy']:.3f}")
    print(f"Precision: {metrics['precision']:.3f}  (of predicted Violence, how many really were)")
    print(f"Recall:    {metrics['recall']:.3f}  (of actual Violence, how many were caught)")
    print(f"F1:        {metrics['f1']:.3f}")
    cm = metrics["confusion_matrix"]
    print("\nConfusion matrix (rows=actual, cols=predicted):")
    print(f"                 Pred NonViolence   Pred Violence")
    print(f"Actual NonViolence     {cm[0][0]:>6}             {cm[0][1]:>6}")
    print(f"Actual Violence        {cm[1][0]:>6}             {cm[1][1]:>6}")

    with open(METRICS_OUT, "w") as f:
        json.dump(metrics, f, indent=2)

    # Save the trained head's weights (plain JSON, not a pickle — small, portable,
    # auditable) so a later integration phase can load it without re-running sklearn.
    with open(MODEL_OUT, "w") as f:
        json.dump(
            {
                "type": "logistic_regression",
                "coef": clf.coef_.tolist(),
                "intercept": clf.intercept_.tolist(),
                "classes": clf.classes_.tolist(),
                "feature_dim": features.shape[1],
                "note": "1 = Violence, 0 = NonViolence. Operates on frozen X3D-S pooled "
                "features (2048-d), see x3d_common.py FeatureExtractor.",
            },
            f,
            indent=2,
        )

    print(f"\nMetrics saved to {METRICS_OUT}")
    print(f"Classifier head saved to {MODEL_OUT}")


if __name__ == "__main__":
    main()
