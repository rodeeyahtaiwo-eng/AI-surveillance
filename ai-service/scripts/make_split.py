"""Build an independent, representative train/validation split — Phase 2C, Step 6.

Two goals that a plain random split would NOT satisfy on its own, given the RLVS
inspection findings:

1. No leakage — each clip is a distinct source video (no shared source across
   train/val), and any self-recorded webcam clips are stratified across both splits
   rather than concentrated in one.
2. The validation set must not reproduce the RLVS production-style confound. A random
   80/20 split of the *filtered* NonViolence set would still be drawn from a pool that's
   ~62.5% non-representative per the Phase 2C spot-check (see
   docs/phase2c-training.md) — meaning a plain random split's validation accuracy would
   still be partly measuring "can it spot broadcast footage," not violence detection.

To address (2) without a full manual re-review of all 250 surviving NonViolence clips
(explicitly out of scope for this timeline), this script treats the specific clips
already individually visually verified during the Phase 2B/2C inspections as a distinct
stratum, ensuring both splits get a fair share of *known-good* examples rather than
leaving it to chance — see VERIFIED_GOOD_NONVIOLENCE below, with a citation for each.

This does not fully solve the underlying scarcity (only 8 NonViolence clips have been
individually verified, out of 250 surviving the filter) — that limitation is reported
honestly in docs/phase2c-training.md, not hidden by this split design.

Usage:
    venv\\Scripts\\python.exe scripts\\make_split.py
"""

import json
import os
import random

import numpy as np

FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "x3d_features.npz")
SPLIT_OUT = os.path.join(os.path.dirname(__file__), "..", "datasets", "split.json")

VAL_FRACTION = 0.2
SEED = 2026

# Individually viewed and judged "plausible/representative real-world footage" during
# the Phase 2B dataset inspection and the Phase 2C stratified spot-check (see
# docs/rlvs-inspection.md and docs/phase2c-training.md for the actual frames/judgment).
VERIFIED_GOOD_NONVIOLENCE = {
    "NV_778.mp4",  # Phase 2B inspection — people outside a shop, candid street scene
    "NV_470.mp4",  # Phase 2B inspection — person walking outdoors, amateur handheld
    "NV_788.mp4",  # Phase 2C spot-check (flagged) — candid street scene
    "NV_764.mp4",  # Phase 2C spot-check (flagged) — candid street scene
    "NV_988.mp4",  # Phase 2C spot-check (flagged) — plausible amateur outdoor footage
    "NV_687.mp4",  # Phase 2C spot-check (control) — captioned candid/social video
    "NV_1.mp4",    # Phase 2C spot-check (control) — candid indoor footage
    "NV_729.mp4",  # Phase 2C spot-check (control) — candid personal video
}


def stratum_for(path: str, label: int, source: str) -> str:
    fname = os.path.basename(path)
    if source == "webcam":
        return "webcam_nonviolence"
    if label == 0 and fname in VERIFIED_GOOD_NONVIOLENCE:
        return "rlvs_nonviolence_verified"
    if label == 0:
        return "rlvs_nonviolence_unverified"
    return "rlvs_violence"


def main() -> None:
    random.seed(SEED)
    data = np.load(FEATURES_PATH, allow_pickle=True)
    paths, labels, sources = data["paths"], data["labels"], data["sources"]

    strata: dict[str, list[int]] = {}
    for i, (path, label, source) in enumerate(zip(paths, labels, sources)):
        s = stratum_for(str(path), int(label), str(source))
        strata.setdefault(s, []).append(i)

    train_idx, val_idx = [], []
    stratum_report = {}
    for stratum, indices in strata.items():
        shuffled = indices[:]
        random.shuffle(shuffled)
        n_val = max(1, round(len(shuffled) * VAL_FRACTION)) if len(shuffled) > 1 else 0
        val_idx.extend(shuffled[:n_val])
        train_idx.extend(shuffled[n_val:])
        stratum_report[stratum] = {"total": len(indices), "train": len(indices) - n_val, "val": n_val}

    split = {
        "seed": SEED,
        "val_fraction": VAL_FRACTION,
        "train_idx": sorted(train_idx),
        "val_idx": sorted(val_idx),
        "stratum_report": stratum_report,
    }
    with open(SPLIT_OUT, "w") as f:
        json.dump(split, f, indent=2)

    print("Split by stratum:")
    for stratum, counts in stratum_report.items():
        print(f"  {stratum}: {counts['total']} total -> train={counts['train']}, val={counts['val']}")

    train_labels = labels[train_idx]
    val_labels = labels[val_idx]
    print(f"\nTrain: {len(train_idx)} ({(train_labels==1).sum()} Violence, {(train_labels==0).sum()} NonViolence)")
    print(f"Val:   {len(val_idx)} ({(val_labels==1).sum()} Violence, {(val_labels==0).sum()} NonViolence)")
    print(f"\nSplit saved to {SPLIT_OUT}")


if __name__ == "__main__":
    main()
