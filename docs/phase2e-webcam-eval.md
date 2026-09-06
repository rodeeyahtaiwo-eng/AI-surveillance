# Phase 2E — Sanity Check: Existing Classifier on Real Webcam Clips

**Status: evaluation only, no retraining.** Uses the Phase 2C classifier exactly as
trained (`datasets/violence_head.json`, unmodified) and the Phase 2C feature-extraction
path exactly as built (`scripts/x3d_common.py`, unmodified). Nothing under `app/`, the
live pipeline, threat scoring, captioning, next-event prediction, or the frontend was
touched. Phase 2C's training artifacts (`x3d_features.npz`, `split.json`,
`violence_head.json`, `violence_head_metrics.json`) were checksummed before and after
this run and are byte-identical — confirmed, not assumed.

## What this is and isn't

This is an **independent sanity check** against the 8 real webcam clips recorded and
fixed in Phase 2D — clips that were never part of the classifier's training set,
validation set, or feature cache. It is explicitly **not** a new accuracy/precision/
recall score: n=8, all from a single unscripted recording session, all one (known,
expected) class, with no independent ground-truth labeling process. A meaningful
accuracy number needs a larger, more varied, properly-labeled sample — this just checks
whether the existing classifier's behavior on genuine deployment footage is at least
consistent with expectation, before any further investment in this direction.

## Results

New artifact: `ai-service/datasets/webcam_clips_eval.json` (separate from all Phase 2C
training artifacts, per the phase instructions).

| File | Decode | Features | Predicted | P(Violence) | P(NonViolence) |
|---|---|---|---|---|---|
| webcam_normal_000.mp4 | OK | OK | NonViolence | 0.0009 | 0.9991 |
| webcam_normal_001.mp4 | OK | OK | NonViolence | 0.0006 | 0.9994 |
| webcam_normal_002.mp4 | OK | OK | NonViolence | 0.0008 | 0.9992 |
| webcam_normal_003.mp4 | OK | OK | NonViolence | 0.0005 | 0.9995 |
| webcam_normal_004.mp4 | OK | OK | NonViolence | 0.0032 | 0.9968 |
| webcam_normal_005.mp4 | OK | OK | NonViolence | 0.0041 | 0.9959 |
| webcam_normal_006.mp4 | OK | OK | NonViolence | 0.0024 | 0.9976 |
| webcam_normal_007.mp4 | OK | OK | NonViolence | 0.0074 | 0.9926 |

**8/8 decoded successfully, 8/8 produced features successfully, 8/8 predicted
NonViolence** — matching the known expected label for this footage, with high and
fairly tight confidence (P(NonViolence) 0.9926–0.9995, no borderline cases near 0.5).

## How to read this, honestly

This is a **pass, not proof**. What it does support: the classifier didn't do anything
alarming or degenerate on real, previously-unseen, deployment-domain footage — it
didn't fail to decode/extract features on non-RLVS-style video, and it didn't
confidently mispredict genuine calm footage as violent. That's a real, useful signal,
and better than the alternative.

What it does **not** support: this says nothing about the harder, still-open question
from `phase2c-training.md` — whether the classifier is keying on genuine
violence-related motion/appearance features or still partly on recording-style cues
(the whole reason for the "read this result with the same skepticism" section there).
Predicting NonViolence correctly on calm footage doesn't distinguish those two
explanations, because a style-shortcut classifier would also predict NonViolence
correctly on calm, non-RLVS-style footage — this test doesn't include a single positive
(violent) example filmed on this webcam, which is the case that would actually
discriminate between the two explanations. That test isn't possible without
deliberately staging or otherwise obtaining violent footage on this camera, which is
its own separate decision, not made here.

## Regression check

`pytest`: 40/40 passing, unchanged. `app/` file mtimes confirm nothing under it was
touched in this phase.
