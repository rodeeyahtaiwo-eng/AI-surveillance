# Phase 2L — Controlled Evaluation of the Existing Firearm Detector

> **Superseded (Phase 2V)**: firearm detection has since been removed from the active
> runtime entirely — see [`phase2v-firearm-removal.md`](phase2v-firearm-removal.md).
> This document is kept as the historical evaluation record that contributed to that
> decision.

**Status: evaluation only. Detector, adapter, confidence threshold (0.5), and Phase 2K
geometry filter (0.9) all unmodified.** No production config was changed. This phase
answers one question with evidence: can the current `firearm_yolov8n.pt` be made
reasonably usable through thresholding/filtering alone, or is the underlying model
itself unsuitable for this webcam surveillance setting? Reproducible via
`ai-service/scripts/evaluate_phase2l_firearm.py`; raw results in
`ai-service/datasets/phase2l_firearm_eval_results.json`.

## A. Dataset/evidence actually available

Two confirmed firearm-**absent** evidence sets, both real webcam footage already in this
project (no synthetic or fabricated data):

1. **"Known false positives" (n=45)** — the Phase 2K evidence set:
   `ai-service/diagnostics/frames/firearm/`, real frames that previously triggered a
   detection. Every one visually inspected (Phase 2K + this phase) and confirmed to
   contain no firearm. **This sample is biased/circular for estimating an overall
   false-positive rate** — it was selected *because* it already triggered — but valid
   for testing whether a candidate filter catches already-known problem cases.
2. **"Unbiased sample" (n=205)** — 5 evenly-spaced frames from each of 41 real webcam
   clips recorded for the unrelated X3D violence-classifier work
   (`datasets/webcam_normal`, `webcam_staged_aggressive`, `webcam_staged_v2`,
   `webcam_validation_v1`), none selected for or against firearm content, none
   containing a firearm (confirmed by their own recording purpose and manifests, Phases
   2C–2I). This is a genuinely unbiased look at the false-positive rate on ordinary
   footage.

**Confirmed firearm-present evidence available: zero images.** The one previously
documented manual smoke test (confidence 0.83, `docs/ai-pipeline.md`) used the model
author's own published example image. That image is not stored in this repository, and
a live fetch of the model's HuggingFace card during this phase found it publishes only
training-curve and confusion-matrix images — no example detection photo, no bounding
box for that 0.83 result either. No RLVS/violence-dataset frame or any other local asset
was substituted for it — doing so would mean guessing at firearm presence in unlabeled
footage, which was explicitly ruled out. **This is reported as a hard limitation, not
worked around by fabricating or repurposing unrelated data as a stand-in.**

## B. Number of confirmed positives

**0 images.** (1 non-reproducible external data point exists in the historical record —
confidence only, no image, no bounding box — insufficient to be called a dataset.)

## C. Number of confirmed negatives

**250 frame evaluations** across the two sets (45 + 205), all confirmed firearm-absent.

## D. Current detector results (unmodified: conf≥0.5, no geometry filter)

| Evidence set | Frames flagged "Gun" | Rate | Confidence range (flagged) | Bbox area-ratio range (flagged) |
|---|---|---|---|---|
| Known false positives (n=45) | 45/45 | 100% | 0.503–0.846 | 0.134–0.999 |
| **Unbiased sample (n=205)** | **54/205** | **26.3%** | 0.504–0.795 | 0.060–0.994 |

The unbiased-sample number is the more meaningful headline figure: **roughly 1 in 4
sampled frames of ordinary/staged-aggressive webcam footage — containing no firearm —
are flagged as "Gun" by the unmodified detector at its current production threshold.**
This is not confined to any one pose or session: hits appear across calm-labeled and
staged-aggressive-labeled clips from three different recording sessions in
`webcam_validation_v1` alone.

## E. Results at each confidence threshold (no geometry filter)

| Threshold | Known FPs remaining (of 45) | Unbiased-sample FPs remaining (of 205) |
|---|---|---|
| 0.50 (current) | 45 (100%) | 54 (26.3%) |
| 0.60 | 28 (62%) | 21 (10.2%) |
| 0.65 | 20 (44%) | 9 (4.4%) |
| 0.70 | 13 (29%) | 5 (2.4%) |
| 0.80 | 1 (2%) | 0 (0%) |
| 0.85 | 0 (0%) | 0 (0%) |
| 0.90 | 0 (0%) | 0 (0%) |

Raising the threshold alone drives false positives toward zero by ~0.80–0.85 on both
sets. **The problem, unchanged from Phase 2K**: the only confirmed genuine detection on
record scored 0.83 — inside the range still needed to fully suppress false positives.
Confidence alone cannot be shown to separate real detections from false ones with the
evidence available.

## F. Results with geometry filtering only (current production default, ratio≤0.9)

| Evidence set | Remaining |
|---|---|
| Known false positives | 18/45 (40%) |
| Unbiased sample | 46/205 (22.4%) |

Consistent with Phase 2K: the geometry filter alone reduces but does not come close to
eliminating the problem on either evidence set.

## G. Results with confidence threshold + geometry filter together

| Threshold | Known FPs: conf-alone → combined | Unbiased: conf-alone → combined |
|---|---|---|
| 0.50 | 45 → 18 | 54 → 46 |
| 0.60 | 28 → 5 | 21 → 16 |
| 0.65 | 20 → 4 | 9 → 4 |
| 0.70 | 13 → **2** | 5 → **1** |
| 0.80 | 1 → **0** | 0 → 0 |
| 0.85 | 0 → 0 | 0 → 0 |

**The two filters are complementary, not redundant** — at 0.70 combined, the known-FP
set drops to 2/45 (96% reduction from the 45/45 baseline) and the unbiased set drops to
1/205 (98% reduction from 54/205), each catching cases the other filter alone misses.
At 0.80 combined, both evidence sets reach zero known false positives.

**Important caveat repeated from Phase 2K, now reinforced**: 0.80 sits below the one
confirmed genuine detection's confidence (0.83), so this combined setting would not, on
paper, have excluded it by confidence — but we have no bounding box for that detection
and therefore cannot confirm it would also pass the geometry filter. This gap is not
closed by this phase; it is the same gap, now with much more false-positive evidence on
the other side of it.

## H. Visual analysis of the false positives that survive current filtering

Every one of the 18 remaining "known false positive" frames (current geometry filter,
no confidence change) was inspected. They group into:

| Group | Count | What's actually in frame |
|---|---|---|
| **No held object at all** — bare hand(s) near face/ear/forehead, or a dark hair/hair-wrap silhouette alone, against a plain wall | **14/18 (78%)** | Nothing resembling a firearm shape is present |
| Holding a smartphone (dark camera lens + rectangular body) | 2/18 (11%) | A phone |
| Holding a glass bottle | 1/18 (6%) | A drink bottle |
| Motion-blurred hand + phone near face | 1/18 (6%) | A phone, blurred |

**This is a significant, evidence-based finding, not a guess**: the dominant confusion
is not "elongated handheld object" (bottle/phone) as the geometry-filter framing might
suggest — it is close-range, selfie-style framing of a hand or dark hair silhouette near
a face against a plain background, **with no object held at all** in over three-quarters
of the surviving cases. This suggests the detector may be responding to close-up
portrait composition and contrast rather than any firearm-specific shape — consistent
with a single-class model trained on a narrow class of images failing to generalize, but
this is an observation about what visual content triggers it, not a claim about the
model's internal reasoning.

## I. What remains unvalidated

- **The detector's true-positive rate is completely unknown.** Zero confirmed
  firearm-present images were evaluated. Every number in this report describes false
  positives only; none of them can be turned into precision, recall, F1, or "accuracy"
  — doing so would require positive examples this project does not have.
- **A combined filter that eliminates all currently-known false positives (conf≥0.80 +
  geometry≤0.9) has never been tested against an actual firearm in this project's own
  camera/lighting/room conditions.** It is not known whether a real firearm, photographed
  under realistic (non-idealized) deployment conditions, would even score above 0.80 —
  the one confirmed reference point (0.83) came from a different, presumably
  well-composed demonstration photo, not this deployment domain.
- Both evidence sets involve one person, in one to two rooms, across a handful of
  sessions — not representative of deployment diversity (different people, skin tones,
  lighting, clothing, camera hardware).
- The model's own card states 89.0% mAP@0.5 on its own curated benchmark and explicitly
  disclaims real-world use ("research purposes only... cannot be used to solve real
  world problems") — unchanged and still directly relevant.

## J. Whether the detector appears usable for this project

**Not established as usable, and the evidence raises real doubt beyond what Phase 2K
already showed.** Two independent findings support this:

1. On a genuinely unbiased sample of ordinary footage, the unmodified detector flags
   roughly **1 in 4 frames** as containing a firearm when none is present. That is a
   severe false-positive rate for a supposedly single-class, purpose-built detector, not
   a rare edge case.
2. The dominant pattern among the false positives that survive current filtering
   involves **no held object whatsoever** — the model is not narrowly confusing
   gun-shaped objects, it appears to be reacting to generic close-range portrait
   composition. That is closer to the signature of a model that has not learned a
   robust, transferable notion of "firearm" than to a well-calibrated detector that
   merely needs its operating point adjusted.

Combined threshold+geometry filtering (§G) can drive the *currently known* false
positives to zero, which is a real, measurable improvement over doing nothing — but
without any confirmed-positive evidence, adopting an aggressive combined filter is a
**mitigation of nuisance alerts**, not a validated restoration of detection capability.
It should not be described as making the detector "accurate" or "reliable."

## Recommended next step

Do not raise the production threshold yet. Two paths forward, not mutually exclusive:

1. **Obtain at least a small set of genuine confirmed-positive evidence** in this
   project's actual deployment conditions — e.g., a safely staged photo/video of a real
   (or clearly inert/replica, if safety or legality is a concern) firearm in the same
   camera/room setup used for the negative evidence above, mirroring how the X3D
   violence work staged its own positive examples (Phases 2D–2I). Without this, no
   threshold or filter change can be validated against false negatives — only against
   false positives.
2. If genuine positive evidence is not obtainable, treat this detector as a
   nuisance-reduction layer only (combined filtering can be adopted for that purpose
   alone, pending the user's review) and keep the existing "unvalidated, not
   safety-critical" framing in `docs/ai-pipeline.md` and `models/README.md` exactly as
   strict as it is today — if anything, this phase's evidence argues for not loosening
   that framing.

No architecture or model-replacement decision is proposed here; per the task, this phase
only establishes whether the current model can be made reasonably usable through
validated thresholding/filtering, and reports that this remains unresolved pending
confirmed-positive evidence.
