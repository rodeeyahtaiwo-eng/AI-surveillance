# Phase 2G — Controlled Positive Retest

**Status: evaluation only, no retraining.** Same frozen classifier and feature path as
Phases 2E/2F, unmodified. Nothing under `app/`, live pipeline, threat scoring,
captioning, next-event prediction, or frontend touched. All prior artifacts
(`x3d_features.npz`, `split.json`, `violence_head.json`, `violence_head_metrics.json`,
`webcam_clips_eval.json`, `webcam_staged_aggressive_eval.json`) checksummed before and
after — byte-identical, confirmed not assumed.

## Recording

3 clips, `datasets/webcam_staged_v2/staged_v2_000–002.mp4` (git-ignored, a third
distinct folder — not merged with Phase 2F's `webcam_staged_aggressive/`, not
referenced by `extract_features.py`/`make_split.py`). Same camera, same `CAP_DSHOW` +
warm-up + 3s countdown as Phase 2F.

## Motion-magnitude verification (against the Phase 2E calm baseline: 0.53–1.41, avg 0.87)

| File | Motion magnitude | vs. calm baseline (max 1.41) | Verdict |
|---|---|---|---|
| staged_v2_000.mp4 | **2.58** | ~1.8× the max | **Clearly elevated** |
| staged_v2_001.mp4 | **2.11** | ~1.5× the max | **Clearly elevated** |
| staged_v2_002.mp4 | 1.19 | within calm range | **Inconclusive** — not treated as a positive example, per the phase instructions |

2 of 3 clips this time show clearly elevated motion (vs. 1 of 6 in Phase 2F) — a better
batch, though clip `_002` is marked inconclusive rather than silently counted as a
positive, exactly as instructed.

## Classifier results

| File | Predicted | P(Violence) | P(NonViolence) | Motion | Status |
|---|---|---|---|---|---|
| **staged_v2_000.mp4** | **Violence** | **0.6702** | 0.3298 | 2.58 | Confirmed positive-motion clip |
| staged_v2_001.mp4 | NonViolence | 0.1254 | 0.8746 | 2.11 | Confirmed positive-motion clip |
| staged_v2_002.mp4 | NonViolence | 0.0105 | 0.9895 | 1.19 | Inconclusive (motion not elevated) |

All 3 decoded and produced features successfully.

## Comparison across all three phases

| Phase | Clips | Confirmed elevated-motion clips | Highest P(Violence) among confirmed clips | Crossed 0.5 threshold? |
|---|---|---|---|---|
| 2E (calm) | 8 | 0 (all calm, as intended) | 0.0074 | No |
| 2F (staged) | 6 | 1 of 6 | 0.0736 | No |
| **2G (staged)** | 3 | **2 of 3** | **0.6702** | **Yes — first time** |

Plotting confirmed-elevated clips by motion magnitude against P(Violence): 2F's `_003`
(motion 6.24) → 0.0736; 2G's `_001` (motion 2.11) → 0.1254; 2G's `_000` (motion 2.58) →
0.6702. This is not a clean monotonic curve (`_003`'s higher motion produced a *lower*
P(Violence) than `_000`'s), so I'm not claiming motion magnitude alone predicts the
score — but every confirmed-elevated clip across both phases scored well above every
calm clip and every inconclusive clip, and this phase produced the first (and so far
only) example that actually crosses into a Violence prediction on this camera.

## How to read this, honestly

**This is the strongest evidence so far that the classifier responds to genuinely
motion-elevated footage, not just recording style** — `staged_v2_000` is real webcam
footage, never seen in training, that the model actually classified as Violence.
That's a materially different result from Phases 2E/2F, where nothing ever crossed the
threshold.

**What it still doesn't establish:**
- **n=1 crossing the threshold, out of 3 confirmed-elevated clips across two phases,
  is a promising signal, not a reliable rate.** I can't tell you this model will
  correctly flag real aggressive motion most of the time from this.
- The non-monotonic relationship between motion magnitude and P(Violence) (`_003`'s
  6.24 scoring lower than `_000`'s 2.58) means motion magnitude is at best a rough
  proxy for whatever the model actually responds to — likely something more specific
  than raw pixel-difference (motion pattern, body pose, framing), which this simple
  metric can't characterize.
- Still staged/mimed, still solo, still one fixed desk-facing camera angle. This
  remains a narrow proxy for a real physical confrontation.
- No attempt was made to determine *why* `_000` crossed and `_001` didn't despite
  similar motion magnitude — that would need more examples and is out of scope for a
  reporting-only phase.

## Regression check

`pytest`: 40/40 passing, unchanged. `app/` file mtimes confirm nothing under it was
touched. All prior Phase 2C/2E/2F artifacts confirmed byte-identical before/after.

## Stopping here

No retraining, no classifier changes, no split changes, no live-system integration —
per the phase instructions. Waiting for approval.
