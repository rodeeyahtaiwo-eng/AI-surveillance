"""Record short local webcam clips for the NonViolence supplementary set — Phase 2C.

Per the approved Phase 2C plan: "a small, clearly documented set of self-recorded
webcam NonViolence clips from the actual deployment webcam/environment." This directly
targets the domain-mismatch finding from the RLVS inspection — RLVS's NonViolence class
is dominated by professionally-produced content, not footage that looks like this
laptop's actual webcam. These clips exist to patch that gap, not to be the bulk of the
training data.

This is a standalone script (not imported by anything in app/ or video-processing) —
kept simple and self-contained rather than cross-importing video-processing's
FrameSource classes, since that's a separate venv/package.

RESOLVED — see docs/phase2d-webcam-fix.md for the full diagnosis. Root cause: the
default OpenCV backend (`cv2.VideoCapture(device)` with no explicit backend, which
resolved to MSMF) has an auto-exposure convergence step that did not finish within the
~2s/30-frame window Phase 2C's clips used — the frames genuinely were dark, but the
camera and room lighting were never the problem. `cv2.CAP_DSHOW` reaches full exposure
by the very first frame (verified: 207.8/255 on frame 1 in diagnostics). This script now
opens the camera with `CAP_DSHOW` explicitly and, as defense-in-depth against any future
driver/backend variance, discards a short warm-up period before recording starts and
measures brightness per clip rather than assuming it's fine.

Usage:
    venv\\Scripts\\python.exe scripts\\record_webcam_clips.py --count 10 --duration 4
"""

import argparse
import os
import time

import cv2
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_normal")
MIN_USABLE_BRIGHTNESS = 25.0  # out of 255 — below this, a clip is flagged unusable, not silently kept
WARMUP_SECONDS = 1.5  # discarded before recording, so exposure has already converged


def record_clip(path: str, duration_s: float, fps: int = 15, device: int = 0) -> dict:
    cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam device {device}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    # Warm-up: read and discard frames so auto-exposure has converged before anything
    # gets written to disk — see the module docstring for why this is needed.
    for _ in range(int(WARMUP_SECONDS * fps)):
        cap.read()

    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    brightness_samples = []
    n_frames = int(duration_s * fps)
    for _ in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        brightness_samples.append(float(frame.mean()))
        writer.write(frame)
        time.sleep(1.0 / fps)

    writer.release()
    cap.release()

    avg_brightness = sum(brightness_samples) / len(brightness_samples) if brightness_samples else 0.0
    return {
        "path": path,
        "frames_written": len(brightness_samples),
        "avg_brightness": avg_brightness,
        "usable": avg_brightness >= MIN_USABLE_BRIGHTNESS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="Number of clips to record")
    parser.add_argument("--duration", type=float, default=4.0, help="Seconds per clip")
    parser.add_argument("--device", type=int, default=0, help="Webcam device index")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for i in range(args.count):
        path = os.path.join(OUTPUT_DIR, f"webcam_normal_{i:03d}.mp4")
        print(f"Recording clip {i + 1}/{args.count} -> {path} ...")
        result = record_clip(path, args.duration, device=args.device)
        results.append(result)
        flag = "OK" if result["usable"] else "UNUSABLE (too dark)"
        print(f"  {result['frames_written']} frames, avg brightness {result['avg_brightness']:.1f}/255 [{flag}]")
        time.sleep(0.5)  # brief pause between clips so they're not all identical

    usable = sum(1 for r in results if r["usable"])
    print(f"\n{usable}/{len(results)} clips usable (brightness >= {MIN_USABLE_BRIGHTNESS}).")
    if usable < len(results):
        print(
            "Some/all clips are too dark to use — check the webcam isn't physically "
            "covered and the room has adequate lighting, then re-run. Unusable clips "
            "are NOT deleted automatically so you can inspect them, but must not be "
            "included in training without addressing this."
        )


if __name__ == "__main__":
    main()
