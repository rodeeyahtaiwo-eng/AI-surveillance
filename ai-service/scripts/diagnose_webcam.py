"""Phase 2D diagnostic — why does the webcam return ~14/255 brightness?

Standalone diagnostic script. Not imported by anything in app/ or video-processing.
Saves preview frames to the scratchpad (not the git-tracked repo) so they can be
visually inspected, and prints camera property values + brightness trend across
backends and exposure settings.
"""

import sys
import time

import cv2
import numpy as np

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."

BACKENDS = [
    ("CAP_ANY (default)", cv2.CAP_ANY),
    ("CAP_DSHOW", cv2.CAP_DSHOW),
    ("CAP_MSMF", cv2.CAP_MSMF),
]


def describe_props(cap) -> dict:
    props = {
        "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
        "brightness": cap.get(cv2.CAP_PROP_BRIGHTNESS),
        "contrast": cap.get(cv2.CAP_PROP_CONTRAST),
        "exposure": cap.get(cv2.CAP_PROP_EXPOSURE),
        "auto_exposure": cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
        "gain": cap.get(cv2.CAP_PROP_GAIN),
        "backend": cap.getBackendName(),
    }
    return props


def try_backend(name: str, backend, device: int = 0, n_frames: int = 30) -> None:
    print(f"\n{'=' * 60}\n{name} (device {device})\n{'=' * 60}")
    cap = cv2.VideoCapture(device, backend)
    if not cap.isOpened():
        print("  Could NOT open device with this backend.")
        return

    props = describe_props(cap)
    print(f"  Initial properties: {props}")

    brightness_trend = []
    last_frame = None
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            print(f"  frame {i}: read FAILED")
            continue
        b = float(frame.mean())
        brightness_trend.append(b)
        last_frame = frame
        time.sleep(1.0 / 15)

    if brightness_trend:
        print(f"  Brightness over {len(brightness_trend)} frames: "
              f"first={brightness_trend[0]:.1f} min={min(brightness_trend):.1f} "
              f"max={max(brightness_trend):.1f} last={brightness_trend[-1]:.1f}")
        print(f"  Per-channel mean of last frame (B,G,R): {last_frame.mean(axis=(0, 1))}")
        print(f"  Pixel value histogram of last frame (min/max/std): "
              f"min={last_frame.min()} max={last_frame.max()} std={last_frame.std():.2f}")
        safe_name = name.split()[0].replace("(", "").replace(")", "")
        out_path = f"{OUT_DIR}/webcam_preview_{safe_name}.png"
        cv2.imwrite(out_path, last_frame)
        print(f"  Saved preview frame: {out_path}")
    else:
        print("  No frames captured at all.")

    cap.release()


def try_forced_exposure(device: int = 0) -> None:
    print(f"\n{'=' * 60}\nCAP_DSHOW with forced auto-exposure + brightness bump\n{'=' * 60}")
    cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("  Could not open.")
        return

    # DirectShow's auto-exposure flag is famously inconsistent across drivers — 0.75 is
    # the common "auto" sentinel value for many UVC webcam drivers (as opposed to 0.25
    # for manual). Try it, plus a manual brightness/gain bump, and see if anything moves.
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    cap.set(cv2.CAP_PROP_BRIGHTNESS, 200)
    cap.set(cv2.CAP_PROP_GAIN, 200)
    time.sleep(1.0)  # let the driver settle after property changes

    props = describe_props(cap)
    print(f"  Properties after forcing auto-exposure/brightness/gain: {props}")

    brightness_trend = []
    last_frame = None
    for i in range(30):
        ok, frame = cap.read()
        if ok:
            brightness_trend.append(float(frame.mean()))
            last_frame = frame
        time.sleep(1.0 / 15)

    if brightness_trend:
        print(f"  Brightness: first={brightness_trend[0]:.1f} last={brightness_trend[-1]:.1f} "
              f"max={max(brightness_trend):.1f}")
        cv2.imwrite(f"{OUT_DIR}/webcam_preview_forced_exposure.png", last_frame)
        print(f"  Saved: {OUT_DIR}/webcam_preview_forced_exposure.png")

    cap.release()


if __name__ == "__main__":
    for name, backend in BACKENDS:
        try_backend(name, backend)
    try_forced_exposure()
