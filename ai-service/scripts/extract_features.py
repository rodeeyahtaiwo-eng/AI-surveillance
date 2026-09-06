"""Extract and cache frozen X3D-S features for all included clips — Phase 2C, Step 4.

Runs once over the filtered dataset so classifier-head iteration (train_classifier.py)
stays cheap — no need to re-run the backbone every time the classifier/split changes.
CPU-only, `torch.set_num_threads(4)` per the Phase 2B benchmark recommendation.

Usage:
    venv\\Scripts\\python.exe scripts\\extract_features.py
"""

import json
import os
import time

import numpy as np
import torch

from x3d_common import FeatureExtractor, clip_tensor_from_video, load_frozen_model

DATASET_ROOT = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs_filter_manifest.json")
WEBCAM_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_normal")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "x3d_features.npz")

MIN_WEBCAM_BRIGHTNESS = 25.0


def gather_items() -> list[dict]:
    """Returns [{path, label, source}] for every clip that should be feature-extracted:
    included RLVS clips (per the filter manifest) + any USABLE self-recorded webcam
    clips. Unusable (too-dark) webcam clips are explicitly excluded, not silently kept
    — see record_webcam_clips.py and docs/phase2c-training.md."""
    items = []

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    for clip in manifest["clips"]:
        if clip["status"] != "included":
            continue
        label = 1 if clip["class"] == "Violence" else 0
        path = os.path.join(DATASET_ROOT, clip["class"], clip["file"])
        items.append({"path": path, "label": label, "source": "rlvs"})

    if os.path.isdir(WEBCAM_DIR):
        for fname in sorted(os.listdir(WEBCAM_DIR)):
            if not fname.endswith(".mp4"):
                continue
            path = os.path.join(WEBCAM_DIR, fname)
            # Re-check brightness at extraction time rather than trusting a stale
            # recording-time flag — cheap, and avoids a class of "the file changed
            # since it was recorded" bugs.
            import cv2

            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame.mean() < MIN_WEBCAM_BRIGHTNESS:
                print(f"  skipping unusable webcam clip: {fname} (too dark)")
                continue
            items.append({"path": path, "label": 0, "source": "webcam"})  # NonViolence

    return items


def main() -> None:
    torch.set_num_threads(4)  # per Phase 2B benchmark recommendation

    print("Loading frozen X3D-S...")
    model = load_frozen_model()
    extractor = FeatureExtractor(model)

    items = gather_items()
    print(f"{len(items)} clips to extract ({sum(1 for i in items if i['label']==1)} Violence, "
          f"{sum(1 for i in items if i['label']==0)} NonViolence)")

    features = []
    labels = []
    sources = []
    paths = []
    failures = []

    t0 = time.time()
    for i, item in enumerate(items):
        try:
            clip = clip_tensor_from_video(item["path"])
            feat = extractor.extract(clip)
        except Exception as exc:  # noqa: BLE001 — log and continue, don't lose the whole run
            failures.append({"path": item["path"], "error": str(exc)})
            continue

        features.append(feat)
        labels.append(item["label"])
        sources.append(item["source"])
        paths.append(item["path"])

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(items) - i - 1) / rate
            print(f"  {i + 1}/{len(items)} done ({rate:.1f} clips/s, ETA {eta/60:.1f} min)")

    features = np.stack(features)
    labels = np.array(labels)
    sources = np.array(sources)
    paths = np.array(paths)

    np.savez(OUT_PATH, features=features, labels=labels, sources=sources, paths=paths)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} min. {len(features)} feature vectors extracted, {len(failures)} failures.")
    if failures:
        print("Failures:")
        for f in failures[:20]:
            print(f"  {f['path']}: {f['error']}")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
