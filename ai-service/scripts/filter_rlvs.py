"""RLVS filtering — Phase 2C, Step 1.

Documented, scripted filtering of the extracted RLVS dataset (ai-service/datasets/rlvs/).
Produces a manifest (JSON) of every clip's disposition and the reason for it — every
inclusion/exclusion decision is traceable, not silent. See docs/phase2c-training.md for
the full rationale and the spot-check evidence behind the 224x224 exclusion policy.

Two independent signals, applied differently per the approved Phase 2C plan:

1. DURATION CAP (automatic exclusion) — evidence-based, not arbitrary. Percentiles
   computed from the full 2,000-clip inspection (see docs/rlvs-inspection.md): p99 is
   7.0s (Violence) / 6.4s (NonViolence), and only 3 clips in the entire dataset exceed
   20s at all (2 Violence, 1 NonViolence — see docs/phase2c-training.md for exactly
   which). A 20s cap removes only these genuine pathological outliers (uncut
   movie/broadcast scenes, not trimmed incidents) without touching any real variation
   in normal clip length.

2. 224x224 SIGNAL (flag for spot-check, NOT automatic exclusion) — per the approved
   plan, this signal only produces a candidate list. The actual exclusion policy for
   NonViolence's flagged clips is a separate, documented decision made from spot-check
   evidence (see spot_check_rlvs.py and docs/phase2c-training.md) — NOT computed by
   this script alone. This script's output distinguishes "flagged, not yet
   adjudicated" from "excluded by decision" so nothing is silently dropped.

Usage:
    venv\\Scripts\\python.exe scripts\\filter_rlvs.py
"""

import json
import os

DATASET_ROOT = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs")
INSPECTION_JSON = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs_inspection.json")
MANIFEST_OUT = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs_filter_manifest.json")

DURATION_CAP_SECONDS = 20.0  # see module docstring for justification
FLAG_RESOLUTION = (224, 224)


def build_manifest() -> dict:
    with open(INSPECTION_JSON) as f:
        inspection = json.load(f)

    manifest = {"clips": [], "summary": {}}

    for cls in ["Violence", "NonViolence"]:
        for row in inspection["results"][cls]:
            duration = row["duration_s"]
            is_224 = (row["width"], row["height"]) == FLAG_RESOLUTION

            if duration and duration > DURATION_CAP_SECONDS:
                status = "excluded"
                reason = f"duration {duration:.1f}s exceeds {DURATION_CAP_SECONDS:.0f}s cap"
            else:
                status = "included"
                reason = "passed duration cap"

            manifest["clips"].append(
                {
                    "class": cls,
                    "file": row["file"],
                    "duration_s": duration,
                    "resolution": [row["width"], row["height"]],
                    "flagged_224": is_224,
                    "status": status,  # "included" | "excluded" — set by THIS script
                    "reason": reason,
                    # Set later by apply_spot_check_decision.py, once the documented
                    # spot-check policy is decided — not touched by this script.
                    "spot_check_decision": None,
                }
            )

    for cls in ["Violence", "NonViolence"]:
        clips = [c for c in manifest["clips"] if c["class"] == cls]
        n_total = len(clips)
        n_excluded_duration = sum(1 for c in clips if c["status"] == "excluded")
        n_flagged_224 = sum(1 for c in clips if c["flagged_224"])
        manifest["summary"][cls] = {
            "total": n_total,
            "excluded_by_duration_cap": n_excluded_duration,
            "flagged_224_for_spot_check": n_flagged_224,
        }

    return manifest


if __name__ == "__main__":
    manifest = build_manifest()
    with open(MANIFEST_OUT, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Duration cap: {DURATION_CAP_SECONDS:.0f}s")
    for cls, summary in manifest["summary"].items():
        print(
            f"{cls}: {summary['total']} total, "
            f"{summary['excluded_by_duration_cap']} excluded (duration), "
            f"{summary['flagged_224_for_spot_check']} flagged 224x224 (needs spot-check, NOT auto-excluded)"
        )
    print(f"\nManifest written to {MANIFEST_OUT}")
