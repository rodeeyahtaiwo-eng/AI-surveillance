# Phase 2F — Same-Camera Positive Test

**Status: evaluation only, no retraining.** Same frozen classifier and feature path as
Phase 2E, unmodified. Nothing under `app/`, the live pipeline, threat scoring,
captioning, next-event prediction, or the frontend was touched. All prior artifacts
(`x3d_features.npz`, `split.json`, `violence_head.json`, `violence_head_metrics.json`,
Phase 2E's `webcam_clips_eval.json`) checksummed before and after this run and are
byte-identical — confirmed, not assumed.

## Why this phase exists

Phase 2E's sanity check could only show the classifier doesn't falsely flag calm
footage as violent — it had no positive (violent-looking) example filmed on this camera
to test against, so it couldn't distinguish "the model learned genuine
violence-related features" from "the model still partly reads recording style." This
phase adds exactly that missing case.

## Recording

6 clips, `datasets/webcam_staged_aggressive/webcam_staged_000.mp4`–`_005.mp4`
(git-ignored, deliberately a **separate folder** from `webcam_normal/` — structurally
excluded from `extract_features.py`/`make_split.py`, neither of which reference it).
Same fixed camera, same `CAP_DSHOW` + warm-up path as Phase 2D, with a 3-second
countdown added before each clip so the person performing had time to get in position
and stop safely between takes. Safety: staged/mimed motion only, no real contact, no
other person required or at risk.

## Honesty check: did the clips actually contain more motion than calm footage?

This script cannot verify what was physically performed in front of the camera, so it
measures mean frame-to-frame pixel difference as an independent, objective signal
before trusting the clips as genuinely "staged aggressive":

| | Motion magnitude |
|---|---|
| Phase 2D calm clips (baseline, n=8) | min 0.53, max 1.41, avg 0.87 |
| Phase 2F staged clips (n=6) | min 0.71, max **6.24**, avg 1.85 |

**Only 1 of the 6 clips (`webcam_staged_003.mp4`, motion magnitude 6.24) shows motion
clearly elevated above the calm baseline** — roughly 7× the baseline average. The other
5 (0.71, 0.84, 0.97, 1.20, 1.15) fall within or barely above the calm range and are not
objectively distinguishable from calm footage by this metric. **I'm reporting this
exactly as measured, not smoothing it over**: this batch produced one clip with
confirmed elevated motion, not six.

## Results — all 6 clips, vs. Phase 2E's calm clips

| File | Predicted | P(Violence) | P(NonViolence) | Motion magnitude |
|---|---|---|---|---|
| webcam_staged_000.mp4 | NonViolence | 0.0002 | 0.9998 | 0.71 |
| webcam_staged_001.mp4 | NonViolence | 0.0002 | 0.9998 | 0.84 |
| webcam_staged_002.mp4 | NonViolence | 0.0004 | 0.9996 | 0.97 |
| **webcam_staged_003.mp4** | NonViolence | **0.0736** | 0.9264 | **6.24** |
| webcam_staged_004.mp4 | NonViolence | 0.0016 | 0.9984 | 1.20 |
| webcam_staged_005.mp4 | NonViolence | 0.0002 | 0.9998 | 1.15 |
| *Phase 2E calm clips (n=8, for reference)* | *all NonViolence* | *0.0005–0.0074* | *0.9926–0.9995* | *0.53–1.41* |

All 6 decoded and produced features successfully. All 6 still classified NonViolence —
none crossed the 0.5 threshold.

## What this does and doesn't support

**The one clip with objectively-confirmed elevated motion (`_003`) also produced the
highest P(Violence) of any clip evaluated across both phases** — 0.0736, roughly
10–50× every other staged clip and above the entire Phase 2E calm range (max 0.0074).
That's a real, directionally-meaningful signal: the classifier's output moved in the
expected direction with motion intensity, on real webcam footage it was never trained
or validated on. It's evidence the model responds to *something* correlated with actual
movement, not a flat near-zero regardless of input — worth having, and better than the
alternative.

**What it doesn't support**, and I'm not going to imply otherwise:
- **n=1 for confirmed elevated motion is not evidence of reliable violence detection.**
  One data point establishes a direction, not a rate.
- The clip still classified NonViolence. Read charitably, that's the model correctly
  not overreacting to a single burst of fast movement (which matters for avoiding false
  alerts in production). Read skeptically, it's the model under-responding to genuinine
  staged aggression. Both readings are consistent with the same number; this test can't
  tell you which is closer to true, and I'm not picking one.
- 5 of 6 clips likely didn't capture the intended staged aggressive motion at all
  (motion magnitude indistinguishable from calm footage) — this is a **data collection
  limitation of this specific session**, not a classifier finding. A future attempt
  might need more deliberate, sustained, larger-amplitude motion, or a longer clip
  duration, to reliably register.
- Still no genuinely violent footage (real or realistically staged with actual
  physical dynamics of a fight) — mimed solo motion at a fixed desk-facing camera is a
  narrow proxy at best for what a real physical confrontation would look like on this
  camera.

## Regression check

`pytest`: 40/40 passing, unchanged. `app/` file mtimes confirm nothing under it was
touched. All Phase 2C/2E artifacts confirmed byte-identical before/after via checksum.

## Stopping here

Per the phase instructions: no retraining, no classifier changes, no split changes, no
live-system integration. Waiting for approval before any further action.
