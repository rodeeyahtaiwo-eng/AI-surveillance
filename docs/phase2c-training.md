# Phase 2C — Bias-Aware Violence Classifier (Frozen X3D-S + Lightweight Head)

**Status: standalone training/evaluation artifact, not yet integrated.** Nothing under
`app/` was modified to produce this. `ACTION_ADAPTER` is still `demo_heuristic` in
production — see [`ai-pipeline.md`](./ai-pipeline.md). See "Not yet integrated" at the
end of this document for exactly what integration would still require.

This phase directly follows up on the domain-bias finding in
[`rlvs-inspection.md`](./rlvs-inspection.md): RLVS's NonViolence class is dominated by
professionally-produced content (sports broadcasts, archival film, TV drama), while
Violence skews amateur/handheld — a production-style confound that risks the model
learning "shaky footage vs. polished broadcast" instead of actual violence-related
features. Every decision below is a documented, evidence-based response to that finding,
not a default pipeline run.

## Step 1 — RLVS filtering (scripted, documented)

Two independent signals, applied differently (`ai-service/scripts/filter_rlvs.py` +
`apply_spot_check_decision.py`):

### Duration cap — automatic, evidence-based

Percentiles computed from the full 2,000-clip inspection: p99 is 7.0s (Violence) / 6.4s
(NonViolence), and **only 3 clips in the entire dataset exceed 20s at all**:

| File | Duration |
|---|---|
| Violence/V_789.mp4 | 375.7s |
| Violence/V_398.mp4 | 137.0s |
| NonViolence/NV_992.mp4 | 179.9s |

A 20s cap removes exactly these 3 pathological outliers (uncut movie/broadcast scenes,
not trimmed incidents) without touching any real variation in normal clip length.

### 224×224 signal — flag for spot-check, NOT automatic exclusion (per the approved plan)

`filter_rlvs.py` only ever *flags* clips at exactly 224×224 (the standard
CNN/ImageNet preprocessing size — a proxy for "this clip has already been through
someone else's pipeline," correlated with, not proof of, non-representative content).
The actual exclusion decision came from a **stratified spot-check**, not the flag alone:

| Group | n | Plausible/representative | Non-representative |
|---|---|---|---|
| NonViolence, flagged (224×224) | 15 | ~3 (20%) | ~12 (80%) — archival B&W film, TV drama, travel/reality shows, talk shows |
| NonViolence, non-flagged (control) | 8 | ~3 (37.5%) | ~5 (62.5%) — still largely sports broadcasts and produced content |
| Violence, flagged (224×224) | 8 | ~3 (37.5%) | ~5 (62.5%) — sports-broadcast scuffles, not archival |
| Violence, non-flagged (control) | 8 | ~4 (50%) | ~4 (50%, mixed sports broadcast/ambiguous) |

Combined with 24 clips already viewed during the Phase 2B inspection (unstratified),
**63/2000 (3.15%) of the dataset was individually viewed** — a deliberate, bounded
sample, not exhaustive review of all 2,000 clips, and not a claim that this proves the
exact population rate.

**Decision (asymmetric by design):**
- **NonViolence: exclude the 224×224-flagged subset (750 clips) entirely, with one
  named exception.** ~80% non-representative in the flagged sample, and individually
  re-sorting ~750 clips wasn't realistic in this timeline. This is a real trade-off: it
  also discards the ~20% genuinely good clips within that flagged set, **and it does
  not fully solve the bias** — the surviving non-flagged NonViolence clips are still
  ~62.5% non-representative per the control-group spot-check.
  **Exception**: of the 8 clips individually viewed and confirmed representative during
  the spot-check itself (see `VERIFIED_GOOD_NONVIOLENCE` in `make_split.py`), 5 happened
  to fall inside the flagged group and would otherwise have been discarded by the
  blanket rule despite having *direct* positive evidence, not a sample-derived
  estimate. `apply_spot_check_decision.py` explicitly re-includes exactly these named
  clips — a class-level heuristic shouldn't override specific evidence we already have,
  and NonViolence is scarce enough (255 of 1000 survive) that this matters. This is a
  deliberate, narrow, named exception, not a loophole — see the script's docstring.
- **Violence: keep the 224×224-flagged subset (no exclusion).** Sports-scuffle footage,
  while stylistically distinct from street-fight footage, still depicts genuine physical
  aggression between people — the actual target concept — unlike NonViolence's
  archival/reality-TV content, which depicts nothing relevant to calm/normal activity.
  Excluding it would also worsen an already-severe class imbalance for no
  corresponding benefit.

**Result:** 998 Violence / 255 NonViolence clips retained (a ~3.9:1 imbalance, handled
explicitly at training time — see Step 6).

## Step 2 — Self-recorded webcam clips: attempted, currently blocked

Per the plan, `ai-service/scripts/record_webcam_clips.py` was built to record short
clips directly from this laptop's webcam for the NonViolence class — targeting the
domain gap no amount of RLVS filtering can fix (RLVS will never look like *this*
webcam, in *this* room).

**Finding, not assumption:** every attempt returned frames with mean brightness
~13-14 out of 255 (essentially black), consistently across:
- the default OpenCV backend and explicit DirectShow (`cv2.CAP_DSHOW`)
- with and without explicit auto-exposure flags
- 15+ consecutive frames (ruling out auto-exposure warm-up — brightness was flat from
  frame 0)

This is consistent with a physically covered lens, a disabled camera, or a genuinely
dark room — not a software/driver issue (same result on two different capture
backends). **3 test clips were recorded and are excluded from training** (the script
measures and reports brightness per-clip specifically so this can't be silently
missed — see `MIN_USABLE_BRIGHTNESS` in `record_webcam_clips.py`).

**Current status: 0 webcam clips included.** The pipeline (`extract_features.py`) checks
for and would automatically include any usable clips placed in
`ai-service/datasets/webcam_normal/` — re-running `record_webcam_clips.py` after
confirming the camera is uncovered and the room is lit, then re-running
`extract_features.py` and `make_split.py`, would pick them up without further code
changes. This is a known, reported gap, not a silently skipped step.

## Step 3 — Frozen backbone, verified

`ai-service/scripts/x3d_common.py` loads X3D-S with `pretrained=True`, `.eval()`, and
`requires_grad_(False)` on every parameter — the backbone is never updated.

The feature-extraction hook point was verified by actually running the model with a
forward hook (not assumed from documentation): `model.blocks[5]` is the
`ResNetBasicHead`; its `.pool` submodule outputs shape `(1, 2048, 1, 2, 2)` for a
`(1, 3, 13, 182, 182)` input. Averaging over the residual spatial dims gives a flat
2048-d feature vector — the standard "penultimate layer" representation for
frozen-backbone transfer learning.

## Step 4 — Feature extraction & caching

`ai-service/scripts/extract_features.py` runs every included clip (998 Violence + 250
NonViolence RLVS, + any usable webcam clips) through the frozen backbone once, caching
`(features, labels, sources, paths)` to `datasets/x3d_features.npz`. `torch.set_num_threads(4)`
per the Phase 2B benchmark recommendation. This is what keeps classifier-head iteration
cheap — the expensive backbone forward pass happens once, not on every training run.

## Step 5 — Validation split (independent, leakage-free, bias-aware)

`ai-service/scripts/make_split.py`. Beyond the basic requirement (no shared source clip
across train/val — each RLVS/webcam file is already a distinct source), this addresses
the second-order risk that a *plain random* 80/20 split of the filtered NonViolence
pool would still be drawn from a set that's ~62.5% non-representative — meaning
validation accuracy would still partly measure "can it spot broadcast footage."

The split stratifies by `(class, verification status, source)`, giving the 8 specific
NonViolence clips individually verified as representative during the Phase 2B/2C visual
inspections their own stratum, so both train and val get a fair share of *known-good*
examples rather than leaving it to chance. **This is a partial mitigation, not a
solution** — only 8 of 250 surviving NonViolence clips have been individually verified;
the rest are split randomly and carry the residual ~62.5% non-representative rate. This
limitation is reported here, not hidden.

## Step 6 — Classifier head

`ai-service/scripts/train_classifier.py`: `sklearn.linear_model.LogisticRegression` on
the cached 2048-d features, `class_weight="balanced"` (the ~4:1 Violence:NonViolence
imbalance left by filtering would otherwise let a trivial majority-class predictor score
misleadingly high raw accuracy — exactly the kind of number this evaluation is designed
to avoid trusting blindly).

## Results

Trained on 1,002 clips (798 Violence / 204 NonViolence), validated on 251 held-out clips
(200 Violence / 51 NonViolence), features cached from 1,253 clips total in 19.2 minutes
(0 extraction failures).

| Metric | Value |
|---|---|
| Accuracy | 0.996 |
| Precision | 0.995 |
| Recall | 1.000 |
| F1 | 0.998 |

Confusion matrix (rows=actual, cols=predicted):

|  | Pred NonViolence | Pred Violence |
|---|---|---|
| **Actual NonViolence** | 50 | 1 |
| **Actual Violence** | 0 | 200 |

### Read this result with the same skepticism that motivated this whole phase

**These numbers are not strong evidence the model generalizes to genuinely
representative footage, and should not be reported as if they were.** Breaking the
validation set down by the stratum defined in Step 5:

| Stratum | Correct | n |
|---|---|---|
| `rlvs_violence` | 200/200 | 100% |
| `rlvs_nonviolence_unverified` | 48/49 | 98.0% |
| `rlvs_nonviolence_verified` | 2/2 | 100.0% |

**49 of the 51 validation NonViolence examples are from the "unverified" stratum** —
the same pool the control-group spot-check found to be ~62.5% non-representative
broadcast/produced content. The overall 99.6% accuracy is therefore dominated by
examples that may still carry the production-style confound this phase set out to
reduce, not eliminate. The `rlvs_nonviolence_verified` stratum (clips individually
confirmed as genuinely representative) has only **2 examples in validation** (6 in
training) — 100% correct on 2 examples is directionally encouraging but statistically
close to meaningless; it neither confirms nor rules out that the classifier is relying
on style cues rather than violence-specific features.

Class separation in the raw probabilities is very clean (Violence median predicted
probability 1.000, NonViolence median 0.001) — consistent with *either* (a) X3D-S's
Kinetics-400-pretrained features genuinely separating high-motion multi-person contact
from calm scenes very well (plausible — this is exactly the kind of thing action
features should capture), *or* (b) the classifier still partly exploiting the
recording-style confound this phase reduced but did not eliminate. **This result cannot
distinguish between those two explanations, and no attempt is made here to claim it
can.** The one validation error (`NonViolence/NV_14.mp4`, predicted Violence at 0.697
probability — an unverified-stratum clip, not individually reviewed) is a borderline
case, not investigated further given the scope of this phase.

**What would actually resolve this**: real footage from the deployment webcam (blocked
this phase — see Step 2) or a larger, fully individually-reviewed NonViolence
validation set (out of scope for this timeline — see Step 1). Until one of those
exists, **treat this classifier as "separates RLVS's own remaining classes very well,"
not as "detects violence in general," let alone "works on this laptop's webcam."**

## Not yet integrated

This phase produces a standalone artifact (`datasets/violence_head.json` — the trained
logistic-regression weights, plus `datasets/x3d_features.npz` and `datasets/split.json`
for reproducibility) and a metrics report. **None of this is wired into
`ai-service/app/`.** A later integration phase would still need to:
- Add a real `X3DActionAdapter` (or similar) implementing `ActionRecognitionAdapter`
  that loads the frozen backbone + this trained head at startup.
- Add the raw-pixel clip buffer described in the earlier architecture investigation
  (the current `CameraWindow` buffers detections, not frames).
- Decide the periodic/gated dispatch cadence (per the Phase 2B benchmark: X3D-S cannot
  run on every sampled frame alongside the two YOLO detectors within the 500ms/2fps
  budget).
- Re-run the full ai-service + backend regression suite after that wiring, the same
  discipline followed in Phase 1's firearm-detector integration.

None of that has happened yet, per the phase instructions.
