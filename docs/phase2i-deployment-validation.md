# Phase 2I — Rigorous Deployment-Domain Validation

**Status: evaluation only. Classifier frozen, unmodified.** No retraining, no threshold
tuning, no adapter/threat-engine/frontend/backend changes. X3D remains disabled by
default (`X3D_ADAPTER=none`). Checksums of `models/violence_head.json`,
`ai-service/datasets/x3d_features.npz`, `split.json`, `violence_head_metrics.json`, and
`app/action_recognition/x3d_violence_adapter.py` were taken before recording, before
evaluation, and after evaluation — all three are byte-identical throughout this phase.

**Correct framing for this whole document: "deployment-domain validation on controlled
webcam footage" — not "real-world violence detection accuracy."** All staged-aggressive
clips are controlled, safe, mimed performances. No genuine violent incident is
represented anywhere in this data. The dataset is small (24 clips). The person
recording, performing, and evaluating is the same person operating the project — this
is not independent third-party validation, and no blind labeling by an uninvolved party
occurred. Nothing here establishes generalization to arbitrary CCTV footage or to real
violence.

## Protocol (fixed before recording, not adjusted after seeing results)

- 24 new clips: 3 sessions × (4 intended-calm + 4 intended-staged-aggressive).
- Same verified CAP_DSHOW + warm-up capture method from Phase 2D — no alternative
  backend was tried or needed.
- **Every clip that decodes counts toward the metrics.** Motion magnitude is recorded
  per clip but was not used to include, exclude, or flag any clip as "inconclusive" —
  unlike Phases 2F/2G, where that filtering happened before reporting. This is the
  central methodological change this phase makes.
- Intended labels were written to the manifest **at recording time**, before the
  classifier was ever run — `ai-service/scripts/record_validation_session.py` writes
  each clip's manifest entry (including `intended_class`) immediately after recording
  it, and the full manifest was saved to disk before `evaluate_phase2i.py` was ever
  invoked.
- One recording pass per session — sessions were not repeated or redone based on
  results (there were no results yet when recording happened).

## Sessions

| Session | Guidance given | Clips |
|---|---|---|
| 1 | Baseline: normal seated distance, facing camera directly | 4 calm + 4 staged |
| 2 | Vary distance/position from Session 1 | 4 calm + 4 staged |
| 3 | Vary lighting/background/clothing from Sessions 1–2 | 4 calm + 4 staged |

**Honest limitation on the variation itself**: this records what guidance was *given*
before each session, not independently confirmed variation — there was no separate
verification that distance/lighting/etc. actually changed by a meaningful amount
between sessions, beyond the fact that each session was a separate recording pass at a
different point in real time.

## Dataset manifest

`ai-service/datasets/webcam_validation_v1/manifest.json` — 24 entries, each with
`clip_id`, `session_id`, `intended_class`, `recorded_at`, `duration_s`, `target_fps`,
`frames_written`, `brightness_avg`, `motion_magnitude`, `session_notes`,
`recording_status`. All 24: `recording_status: "ok"`, 60/60 frames, brightness
109–135/255 (well above the usability floor established in Phase 2D).

12 intended-calm, 12 intended-staged-aggressive. **Zero recording failures.**

## Model/checkpoint identity

- Classifier: `models/violence_head.json`, md5 `fcb636bd1b917409a495faf10c38eecb` —
  identical to every checksum recorded since Phase 2E.
- Backbone: frozen X3D-S, Kinetics-400 pretrained, loaded via
  `torch.hub.load("facebookresearch/pytorchvideo", "x3d_s", pretrained=True)`, unchanged
  since Phase 2B.
- Preprocessing: `scripts/x3d_common.py`'s `clip_tensor_from_video` (13-frame uniform
  subsample, 182×182 center crop, `mean=[0.45]*3`/`std=[0.225]*3` normalize) —
  unmodified since Phase 2C, and already checksum-verified in Phase 2H to reproduce the
  live pipeline path exactly.

## Evaluation procedure

`ai-service/scripts/evaluate_phase2i.py` — reuses `evaluate_webcam_clips.py`'s exact
prediction function (`sigmoid(coef · features + intercept)`) and `x3d_common.py`'s
exact feature extraction. Every one of the 24 manifest entries was scored in a single
pass; results written to `datasets/webcam_validation_v1/evaluation_results.json`.

## All 24 individual results

| Clip | Session | Intended | Motion | Predicted | P(Violence) | Correct? |
|---|---|---|---|---|---|---|
| s1_calm_00 | 1 | calm | 1.06 | NonViolence | 0.1970 | ✅ |
| s1_calm_01 | 1 | calm | 1.31 | NonViolence | 0.3182 | ✅ |
| s1_calm_02 | 1 | calm | 0.93 | NonViolence | 0.1915 | ✅ |
| s1_calm_03 | 1 | calm | 2.88 | NonViolence | 0.1922 | ✅ |
| s1_staged_aggressive_00 | 1 | staged_aggressive | 6.33 | NonViolence | 0.0245 | ❌ |
| s1_staged_aggressive_01 | 1 | staged_aggressive | 1.33 | NonViolence | 0.1255 | ❌ |
| s1_staged_aggressive_02 | 1 | staged_aggressive | 2.17 | NonViolence | 0.0275 | ❌ |
| s1_staged_aggressive_03 | 1 | staged_aggressive | 1.45 | NonViolence | 0.0337 | ❌ |
| s2_calm_00 | 2 | calm | 3.35 | NonViolence | 0.0525 | ✅ |
| s2_calm_01 | 2 | calm | 1.40 | NonViolence | 0.0042 | ✅ |
| s2_calm_02 | 2 | calm | 4.85 | NonViolence | 0.0622 | ✅ |
| s2_calm_03 | 2 | calm | 1.04 | NonViolence | 0.0002 | ✅ |
| s2_staged_aggressive_00 | 2 | staged_aggressive | 1.35 | NonViolence | 0.0064 | ❌ |
| s2_staged_aggressive_01 | 2 | staged_aggressive | 0.70 | NonViolence | 0.0024 | ❌ |
| s2_staged_aggressive_02 | 2 | staged_aggressive | 1.04 | NonViolence | 0.0032 | ❌ |
| s2_staged_aggressive_03 | 2 | staged_aggressive | 0.84 | NonViolence | 0.0028 | ❌ |
| s3_calm_00 | 3 | calm | 0.96 | NonViolence | 0.0006 | ✅ |
| s3_calm_01 | 3 | calm | 0.94 | NonViolence | 0.0002 | ✅ |
| s3_calm_02 | 3 | calm | 0.67 | NonViolence | 0.0038 | ✅ |
| s3_calm_03 | 3 | calm | 1.24 | NonViolence | 0.0039 | ✅ |
| s3_staged_aggressive_00 | 3 | staged_aggressive | 1.04 | NonViolence | 0.0012 | ❌ |
| s3_staged_aggressive_01 | 3 | staged_aggressive | **11.22** | NonViolence | **0.0195** | ❌ |
| s3_staged_aggressive_02 | 3 | staged_aggressive | 3.89 | NonViolence | 0.0167 | ❌ |
| s3_staged_aggressive_03 | 3 | staged_aggressive | 1.88 | NonViolence | 0.0373 | ❌ |

Recording failures: 0. Decode failures: 0. Feature-extraction failures: 0.

## Aggregate metrics — overall (n=24)

| Metric | Value |
|---|---|
| Accuracy | **0.500** |
| Precision | **0.000** |
| Recall | **0.000** |
| F1 | **0.000** |

Confusion matrix (rows = intended, columns = predicted):

|  | Predicted NonViolence | Predicted Violence |
|---|---|---|
| **Intended calm** | 12 (TN) | 0 (FP) |
| **Intended staged-aggressive** | 12 (FN) | 0 (TP) |

**The classifier predicted NonViolence on all 24 clips, with no exceptions.** 100% of
intended-calm clips were correctly read as NonViolence. 0% of intended-staged-aggressive
clips were read as Violence — every one of the 12 is a false negative.

## Per-session results

| Session | n | Accuracy | Precision | Recall | F1 | TP/FP/TN/FN |
|---|---|---|---|---|---|---|
| 1 | 8 | 0.500 | 0.000 | 0.000 | 0.000 | 0/0/4/4 |
| 2 | 8 | 0.500 | 0.000 | 0.000 | 0.000 | 0/0/4/4 |
| 3 | 8 | 0.500 | 0.000 | 0.000 | 0.000 | 0/0/4/4 |

Identical across all three sessions — no session/condition produced a single positive
prediction.

## What this means — stated plainly, not softened

This is a materially weaker result than Phases 2F–2G suggested, and that gap is the
actual finding of this phase. Phase 2G's one threshold-crossing clip (motion 2.58 →
P(Violence)=0.67) does not replicate here: `s3_staged_aggressive_01` has *higher* motion
magnitude (11.22, the highest recorded in this entire phase) and scored **0.0195** —
essentially the same near-zero range as every calm clip. Motion magnitude and
P(Violence) show no usable relationship in this dataset; the earlier "promising"
Phase 2G result now looks more like an isolated data point than an early sign of a
working relationship.

**Why the earlier phases looked more encouraging**: Phases 2F/2G reported results only
for clips with independently-confirmed elevated motion, which felt like an objective
inclusion criterion but was still a form of selecting after the fact — and even within
that already-narrowed set, only 1 of 4 confirmed-elevated clips across both phases
crossed the threshold. This phase's "everything counts" rule removes that selection
effect entirely, and the result is that **recall on intended-staged-aggressive footage
is 0.0** when nothing is filtered out first.

**What this does not mean**: it doesn't mean the classifier is "broken" or contradicts
Phase 2C's training-time metrics — those numbers describe performance on RLVS's
distribution, not this one, and were already flagged there as not translating directly
to deployment footage. It also doesn't mean the frozen backbone features are useless —
Phase 1's firearm detector and general YOLO remain fully real and unaffected, and this
result is specific to the small trained head on this specific task. What it does mean:
**on this evidence, this classifier should not be relied on to detect the kind of
staged aggressive motion recorded in this phase, on this camera, today.**

## Limitations (restated explicitly, per the phase instructions)

- All staged-aggressive examples are controlled, safe, and mimed — not genuine
  violence, and not a validated proxy for it.
- n=24 is small; a single-digit change in a few predictions would shift the metrics
  substantially.
- The recorder, performer, and evaluator are the same person operating this project —
  not independent, not blinded.
- No genuine physical altercation, no second person, no varied real-world camera
  placement is represented.
- This does not establish or rule out generalization to arbitrary CCTV footage or real
  incidents.

## Historical Phase 2D–2H deployment evidence (kept separate — not merged with the above)

This is exploratory, motion-filtered evidence from earlier phases, reported here for
context only. **It is not part of the Phase 2I 24-clip formal set and the numbers below
must not be combined with it.**

- **Phase 2D/2E**: 8 real calm webcam clips recorded and verified decode-clean; all 8
  correctly classified NonViolence by the frozen classifier.
- **Phase 2F**: 6 staged safe clips; only 1 showed independently-confirmed elevated
  motion (others were motion-filtered as inconclusive, not included in Phase 2I's
  no-filtering approach). That 1 clip scored 0.0736 — well above the calm range, but
  did not cross the 0.5 decision threshold.
- **Phase 2G**: 3 more staged clips; 2 showed confirmed elevated motion. One of those
  two (motion 2.58) crossed the threshold at P(Violence)=0.6702 — the only confirmed
  "Violence" prediction across all of Phases 2D–2I combined (41 total clips across every
  phase, calm + staged + this phase's 24).
- **Phase 2H**: live-pipeline adapter re-evaluated on all 17 of the above; reproduced
  the offline results exactly (0.0000 difference on every clip) — a check on
  implementation consistency, not on classifier accuracy.

**Taken together with Phase 2I**: across 29 total staged-aggressive attempts recorded
across Phases 2F, 2G, and 2I (6 + 3 + 12 — not statistically pooled here, just counted),
exactly **one** produced a Violence prediction. That is the honest current state of
evidence for this classifier's sensitivity to aggressive motion on this camera.

## Regression check

`ai-service` tests: 67/67 passing, unchanged. `backend` tests: 21/21 passing, unchanged.
`X3D_ADAPTER` still defaults to `"none"`. No files under `app/` were modified except
new test/script additions already covered by Phase 2H — this phase touched only new
scripts (`record_validation_session.py`, `evaluate_phase2i.py`) and new data/docs.
Frontend: untouched. Threat engine: untouched.

## Stopping here

Per the phase instructions: no retraining, no threshold tuning, no integration changes,
no proceeding to a further phase. Waiting for approval.
