"""Phase 2H manual smoke test — NOT an automated test, loads real X3D-S weights.

Runs the LIVE PIPELINE's X3DViolenceAdapter (app/action_recognition/
x3d_violence_adapter.py) against the real webcam clips already recorded in Phases
2E-2G, and checks its predictions against what scripts/evaluate_webcam_clips.py already
found using the offline training-side path (scripts/x3d_common.py). The two
preprocessing implementations are deliberately duplicated (see both files' docstrings
for why) — this is the check that they haven't drifted apart.

Does not add these clips to training, does not modify the classifier, does not touch
app/ or any Phase 2C-2G artifact. Same precedent as the firearm detector's manual smoke
test and Phase 2B's benchmark script — real-weight verification stays manual, not CI.

Usage:
    venv\\Scripts\\python.exe scripts\\smoke_test_live_x3d_adapter.py
"""

import json
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INGEST_API_KEY", "smoke-test-only-not-for-prod-1234567890")
os.environ.setdefault("X3D_ADAPTER", "x3d_violence")

from app.action_recognition.x3d_violence_adapter import X3DViolenceAdapter  # noqa: E402

CLIP_SETS = {
    "Phase 2E (calm)": "../datasets/webcam_normal",
    "Phase 2F (staged)": "../datasets/webcam_staged_aggressive",
    "Phase 2G (staged retest)": "../datasets/webcam_staged_v2",
}

# What scripts/evaluate_webcam_clips.py already found (P(Violence)), for comparison —
# hand-transcribed from docs/phase2e-webcam-eval.md, docs/phase2f-staged-positive-test.md,
# docs/phase2g-controlled-retest.md.
OFFLINE_RESULTS = {
    "webcam_normal_000.mp4": 0.0009, "webcam_normal_001.mp4": 0.0006,
    "webcam_normal_002.mp4": 0.0008, "webcam_normal_003.mp4": 0.0005,
    "webcam_normal_004.mp4": 0.0032, "webcam_normal_005.mp4": 0.0041,
    "webcam_normal_006.mp4": 0.0024, "webcam_normal_007.mp4": 0.0074,
    "webcam_staged_000.mp4": 0.0002, "webcam_staged_001.mp4": 0.0002,
    "webcam_staged_002.mp4": 0.0004, "webcam_staged_003.mp4": 0.0736,
    "webcam_staged_004.mp4": 0.0016, "webcam_staged_005.mp4": 0.0002,
    "staged_v2_000.mp4": 0.6702, "staged_v2_001.mp4": 0.1254, "staged_v2_002.mp4": 0.0105,
}


def frames_from_video(path: str):
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def main() -> None:
    print("Loading REAL X3D-S backbone + trained classifier head (live pipeline path)...")
    adapter = X3DViolenceAdapter()
    print("Loaded.\n")

    max_diff = 0.0
    n_compared = 0
    n_matched_class = 0

    for set_name, rel_dir in CLIP_SETS.items():
        clip_dir = os.path.join(os.path.dirname(__file__), rel_dir)
        if not os.path.isdir(clip_dir):
            print(f"{set_name}: directory not found ({clip_dir}), skipping")
            continue

        print(f"--- {set_name} ---")
        for fn in sorted(f for f in os.listdir(clip_dir) if f.endswith(".mp4")):
            path = os.path.join(clip_dir, fn)
            frames = frames_from_video(path)
            observation = adapter.recognize([], clip_frames=frames)
            live_prob = observation.metrics["x3d_prob_violence"]

            offline_prob = OFFLINE_RESULTS.get(fn)
            if offline_prob is not None:
                diff = abs(live_prob - offline_prob)
                max_diff = max(max_diff, diff)
                n_compared += 1
                offline_class = "Violence" if offline_prob >= 0.5 else "NonViolence"
                live_class = "Violence" if live_prob >= 0.5 else "NonViolence"
                if offline_class == live_class:
                    n_matched_class += 1
                print(f"  {fn}: live P(violence)={live_prob:.4f}  offline={offline_prob:.4f}  "
                      f"diff={diff:.4f}  predicted={live_class} (offline said {offline_class})")
            else:
                print(f"  {fn}: live P(violence)={live_prob:.4f}  (no offline reference on file)")

    print(f"\nCompared {n_compared} clips against offline results.")
    print(f"Predicted class agreement: {n_matched_class}/{n_compared}")
    print(f"Max |live - offline| probability difference: {max_diff:.4f}")
    if max_diff < 0.01:
        print("PASS — live pipeline path reproduces the offline path to within floating-point noise.")
    elif n_matched_class == n_compared:
        print("PASS (with numeric drift) — class predictions agree but probabilities differ more than "
              "expected; worth investigating before relying on close-to-threshold cases.")
    else:
        print("MISMATCH — live and offline paths disagree on at least one predicted class. "
              "Investigate before enabling X3D_ADAPTER=x3d_violence.")


if __name__ == "__main__":
    main()
