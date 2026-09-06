"""Phase 2F — record a small number of SAFE, staged aggressive/fighting-action clips
on the same webcam, as a positive-class sanity check. This is the counterpart to
Phase 2D's calm NonViolence clips: Phase 2E could only show the classifier doesn't
falsely flag calm footage, because it had no positive example filmed on this camera to
test against — see docs/phase2e-webcam-eval.md "How to read this, honestly".

SAFETY: staged only. No real other person is required or should be put at risk — think
shadow-boxing, mock/air punches and kicks, exaggerated rapid arm/body movement aimed at
nothing and no one, performed solo at a safe distance from any object or person. No
real contact, no real risk, ever. This script adds a visible countdown before each clip
so whoever is performing has time to get ready and stop safely between clips.

Saved to a DELIBERATELY SEPARATE folder (datasets/webcam_staged_aggressive/, not
webcam_normal/) so it is structurally impossible for these to be silently picked up by
extract_features.py, make_split.py, or train_classifier.py, none of which reference
this folder. Per the phase instructions, these clips are NOT added to the training set.

Reuses the same CAP_DSHOW + warm-up fix from Phase 2D (see docs/phase2d-webcam-fix.md)
rather than duplicating a second, potentially-inconsistent recording path — this file
imports record_clip() from record_webcam_clips.py instead of reimplementing it.

Usage:
    venv\\Scripts\\python.exe scripts\\record_staged_positive_clips.py --count 6 --duration 4
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from record_webcam_clips import record_clip  # noqa: E402 — reuse the fixed capture path exactly

DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_staged_aggressive")
COUNTDOWN_SECONDS = 3


def motion_magnitude(path: str) -> float:
    """Mean absolute frame-to-frame pixel difference — an objective, independent check
    that a clip actually contains more movement than a calm clip, since this script
    cannot verify what was physically performed in front of the camera. Not used by the
    classifier; purely a sanity signal for this report."""
    cap = cv2.VideoCapture(path)
    prev = None
    diffs = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            diffs.append(float(np.abs(gray - prev).mean()))
        prev = gray
    cap.release()
    return sum(diffs) / len(diffs) if diffs else 0.0


def countdown(seconds: int) -> None:
    for i in range(seconds, 0, -1):
        print(f"  starting in {i}...", flush=True)
        time.sleep(1)
    print("  RECORDING NOW — perform the staged action (safely, solo, no real contact)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=6, help="Number of clips to record")
    parser.add_argument("--duration", type=float, default=4.0, help="Seconds per clip")
    parser.add_argument("--device", type=int, default=0, help="Webcam device index")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Folder to save clips into")
    parser.add_argument("--prefix", default="webcam_staged", help="Filename prefix")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 70)
    print("SAFETY REMINDER: staged/mimed aggressive motion only. No real contact,")
    print("no real other person needed or at risk. Solo shadow-boxing / air punches /")
    print("rapid exaggerated movement aimed at nothing. Stop immediately if unsafe.")
    print("=" * 70)

    results = []
    for i in range(args.count):
        path = os.path.join(output_dir, f"{args.prefix}_{i:03d}.mp4")
        print(f"\nClip {i + 1}/{args.count} -> {path}")
        countdown(COUNTDOWN_SECONDS)
        result = record_clip(path, args.duration, device=args.device)
        motion = motion_magnitude(path) if result["frames_written"] > 0 else 0.0
        result["motion_magnitude"] = motion
        results.append(result)
        flag = "OK" if result["usable"] else "UNUSABLE (too dark)"
        print(f"  {result['frames_written']} frames, avg brightness {result['avg_brightness']:.1f}/255 "
              f"[{flag}], motion magnitude {motion:.2f}")
        time.sleep(1.0)  # pause between clips

    usable = sum(1 for r in results if r["usable"])
    print(f"\n{usable}/{len(results)} clips usable (brightness check).")

    motions = [r["motion_magnitude"] for r in results]
    print(f"Motion magnitude across clips: min={min(motions):.2f} max={max(motions):.2f} "
          f"avg={sum(motions)/len(motions):.2f}")
    print(
        "Compare this to Phase 2D's calm clips before trusting these as genuinely "
        "'staged aggressive' rather than another calm session — see the chat report."
    )


if __name__ == "__main__":
    main()
