"""Apply the documented spot-check exclusion policy — Phase 2C, Step 1 (continued).

This is a SEPARATE step from filter_rlvs.py by design: filter_rlvs.py only ever
*flags* 224x224 clips, per the approved plan ("use the 224x224 signal only to flag
candidates for spot-checking, not as an automatic exclusion rule"). This script applies
the actual, human-reviewed decision — see docs/phase2c-training.md "Filtering
decisions" for the full spot-check methodology and evidence.

SPOT-CHECK METHODOLOGY (summary — full detail in docs/phase2c-training.md):
Stratified random sample, flagged vs. non-flagged, both classes: 15 flagged
NonViolence, 8 non-flagged NonViolence (control), 8 flagged Violence, 8 non-flagged
Violence (control) = 39 clips, reviewed via contact-sheet grids of each clip's middle
frame. Combined with 24 clips already viewed in the Phase 2B dataset inspection
(unstratified), total 63/2000 (3.15%) visually reviewed — not exhaustive, but a
deliberate, bounded, documented sample, per the instruction not to hand-review all
2,000 videos.

FINDINGS (see docs/phase2c-training.md for the itemized breakdown):
- NonViolence flagged (224x224): ~15-20% plausible/representative footage, ~80-85%
  non-representative (archival B&W film, TV drama, travel/reality shows, talk shows).
- NonViolence non-flagged (control): ~37.5% plausible, ~62.5% non-representative
  (still largely professional sports broadcasts and produced content) — meaning the
  224x224 flag is correlated with the problem but is NOT a clean separator; a
  meaningful share of the bias exists outside the flagged set too.
- Violence flagged (224x224): dominated by sports-broadcast scuffles (~62.5%), not
  archival content — a different, less severe failure mode (still genuine physical
  aggression between people, just in a stadium/broadcast context).
- Violence non-flagged (control): ~50% clearly genuine street-altercation footage.

DECISION (asymmetric by design, reasoned from the above):
1. NonViolence: EXCLUDE the 224x224-flagged subset entirely. Evidence-based
   (~80% non-representative in the flagged sample) and the cost of manually sorting
   ~750 individual clips is not justified in this project's timeline. This is a real,
   acknowledged trade-off — it also discards some genuinely good clips (the ~15-20%)
   as a side effect, and does NOT fully solve the bias (the surviving non-flagged
   NonViolence clips are still ~62.5% non-representative per the control spot-check).
   This residual bias is why self-recorded webcam clips and a deliberately
   representative validation split (later steps) matter — this filter step alone does
   not fix the problem.
2. Violence: KEEP the 224x224-flagged subset. Sports-scuffle footage, while
   stylistically distinct from street-fight footage, still depicts genuine physical
   aggression between people — the actual target concept — unlike NonViolence's
   archival/reality-TV content, which depicts nothing relevant to "calm/normal
   activity" in a way that matches real deployment conditions. Excluding it would
   also worsen an already-severe class imbalance for no corresponding accuracy benefit.

Usage:
    venv\\Scripts\\python.exe scripts\\apply_spot_check_decision.py

EXCEPTION — individually-verified clips override the blanket flag policy: the
224x224-based exclusion is a *class-level* rule derived from a *sample's* evidence
(~80% non-representative), not a per-clip judgment — it necessarily also discards the
~20% good clips within that flagged set, acknowledged in docs/phase2c-training.md as a
real trade-off. But for the specific handful of clips that were *individually viewed
and confirmed good* during the spot-check itself, we have direct evidence, not a
sample-derived estimate — and NonViolence is the scarce resource here (250 of 1000
survive at all). Overriding the blanket rule for exactly these named clips is more
consistent with "evidence-based, not blind rules" than letting the class-level
heuristic discard clips we've directly confirmed. See VERIFIED_GOOD_NONVIOLENCE in
make_split.py for the citation of each.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from make_split import VERIFIED_GOOD_NONVIOLENCE  # noqa: E402

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "rlvs_filter_manifest.json")


def apply_decision() -> dict:
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    for clip in manifest["clips"]:
        if clip["status"] == "excluded":
            clip["spot_check_decision"] = "n/a (already excluded by duration cap)"
            continue

        is_individually_verified = clip["class"] == "NonViolence" and clip["file"] in VERIFIED_GOOD_NONVIOLENCE

        if clip["class"] == "NonViolence" and clip["flagged_224"] and not is_individually_verified:
            clip["status"] = "excluded"
            clip["spot_check_decision"] = (
                "excluded — 224x224 flag + spot-check evidence (~80% non-representative "
                "in stratified sample, see docs/phase2c-training.md)"
            )
            clip["reason"] = "excluded by documented spot-check policy (NonViolence, 224x224-flagged)"
        elif is_individually_verified:
            clip["spot_check_decision"] = (
                "kept — individually verified good despite 224x224 flag (direct evidence "
                "overrides the class-level policy, see module docstring)"
            )
        else:
            clip["spot_check_decision"] = (
                "kept — not flagged, or flagged-but-Violence (kept per asymmetric policy, "
                "see docs/phase2c-training.md)"
            )

    for cls in ["Violence", "NonViolence"]:
        clips = [c for c in manifest["clips"] if c["class"] == cls]
        included = [c for c in clips if c["status"] == "included"]
        manifest["summary"][cls]["final_included"] = len(included)
        manifest["summary"][cls]["final_excluded"] = len(clips) - len(included)

    return manifest


if __name__ == "__main__":
    manifest = apply_decision()
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print("Final manifest after spot-check policy applied:")
    for cls, summary in manifest["summary"].items():
        print(f"  {cls}: {summary['final_included']} included, {summary['final_excluded']} excluded")
    print(f"\nManifest updated at {MANIFEST_PATH}")
