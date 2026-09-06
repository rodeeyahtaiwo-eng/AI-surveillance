"""Phase 2I — records one session of the rigorous 24-clip deployment-domain validation
set: 4 intended-calm + 4 intended-staged-aggressive clips, written to
datasets/webcam_validation_v1/ with a manifest entry per clip recording its INTENDED
label at recording time (before any classifier evaluation happens).

Reuses the exact verified capture path from Phase 2D (record_clip, CAP_DSHOW + warm-up)
and the exact motion-magnitude/countdown helpers from Phase 2F — no new camera-handling
logic is introduced here, per the phase instructions ("do not experiment with
alternative camera backends unless the verified method fails").

Per the Phase 2I protocol: motion magnitude is recorded for every clip but is NOT used
to include/exclude anything here or later — every clip that decodes goes into the
manifest and later into evaluation, full stop.

Usage:
    venv\\Scripts\\python.exe scripts\\record_validation_session.py --session 1
    venv\\Scripts\\python.exe scripts\\record_validation_session.py --session 2
    venv\\Scripts\\python.exe scripts\\record_validation_session.py --session 3
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from record_staged_positive_clips import countdown, motion_magnitude  # noqa: E402
from record_webcam_clips import record_clip  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "webcam_validation_v1")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "manifest.json")

SESSION_GUIDANCE = {
    1: "Baseline: normal seated distance from the camera, facing it directly.",
    2: "Vary distance/position from Session 1 — try a bit closer for some clips and a "
    "bit farther for others; consider a different seating/standing position or angle.",
    3: "Vary lighting/background/clothing from Sessions 1-2 where practical (e.g. "
    "different room lighting or time of day, a different visible background).",
}


def load_manifest() -> list:
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return []


def save_manifest(entries: list) -> None:
    with open(MANIFEST_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def record_block(session: int, intended_class: str, count: int, duration: float, device: int, entries: list) -> None:
    is_staged = intended_class == "staged_aggressive"
    label = "STAGED-AGGRESSIVE (safe, staged, no real contact)" if is_staged else "CALM"
    print(f"\n{'=' * 70}\nSession {session} — {label} block ({count} clips)\n{'=' * 70}")
    if is_staged:
        print("SAFETY: staged/mimed motion only. No real contact, no other person at risk.")

    for i in range(count):
        clip_id = f"s{session}_{intended_class}_{i:02d}"
        path = os.path.join(OUTPUT_DIR, f"{clip_id}.mp4")
        print(f"\nClip {clip_id} -> {path}")
        countdown(3)
        result = record_clip(path, duration, device=device)
        motion = motion_magnitude(path) if result["frames_written"] > 0 else 0.0

        entry = {
            "clip_id": clip_id,
            "file": f"{clip_id}.mp4",
            "session_id": session,
            "intended_class": intended_class,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": duration,
            "target_fps": 15,
            "frames_written": result["frames_written"],
            "brightness_avg": round(result["avg_brightness"], 1),
            "motion_magnitude": round(motion, 3),
            "session_notes": SESSION_GUIDANCE[session],
            "recording_status": "ok" if result["frames_written"] > 0 else "recording_failed",
        }
        entries.append(entry)
        save_manifest(entries)  # persist after every clip, not just at the end

        print(f"  frames={result['frames_written']} brightness={result['avg_brightness']:.1f}/255 "
              f"motion_magnitude={motion:.2f} status={entry['recording_status']}")
        print("  (motion magnitude recorded for reference only — NOT used to include/exclude this clip)")
        time.sleep(1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, required=True, choices=[1, 2, 3])
    parser.add_argument("--calm-count", type=int, default=4)
    parser.add_argument("--staged-count", type=int, default=4)
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    entries = load_manifest()

    existing_for_session = [e for e in entries if e["session_id"] == args.session]
    if existing_for_session:
        print(f"WARNING: {len(existing_for_session)} manifest entries already exist for "
              f"session {args.session}. Re-running will add more, not replace them.")

    print(f"\nSession {args.session} guidance: {SESSION_GUIDANCE[args.session]}")

    record_block(args.session, "calm", args.calm_count, args.duration, args.device, entries)
    record_block(args.session, "staged_aggressive", args.staged_count, args.duration, args.device, entries)

    print(f"\nSession {args.session} complete. Manifest now has {len(entries)} total entries "
          f"across all sessions run so far -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
