# Phase 2Q — S3D / BLIP / Temporal Predictor Feasibility Spike

**Status: feasibility test only. Nothing integrated into production.** No production
code, `.env` default, firearm configuration, or X3D setting was changed. The existing
application is untouched and fully intact. Two new Python packages (`transformers` and
its small dependency tree) were installed into `ai-service`'s venv to run the BLIP test
— nothing else was modified. All numbers below are real measurements from this exact
machine, not estimates.

## Part A — Environment inspection

| | Value |
|---|---|
| Python | 3.12.4 |
| torch | 2.13.0+cpu |
| torchvision | 0.28.0+cpu |
| ultralytics | 8.3.0 |
| opencv-python | 4.11.0 |
| numpy | 1.26.4 |
| transformers | **not installed** before this phase → installed 5.16.1 for the BLIP test |
| Free disk space, measured at the start of this phase | **12.04 GB** |
| Free disk space, measured at the end of this phase | 17.20 GB (see note below) |

**Note on the disk space change**: free space increased over the course of this phase
despite two real downloads (S3D weights + BLIP weights + transformers). This was not
caused by anything this phase did — something else on the machine freed space
independently during the same window. Reported as measured, not adjusted or explained
away.

**Existing interfaces inspected** (so any eventual integration preserves the current
contract):
- `ActionRecognitionAdapter.recognize(window: List[Tuple[datetime, List[DetectionResult]]], clip_frames: Optional[List[np.ndarray]] = None) -> ActionObservation` (`app/action_recognition/base.py`) — already accepts raw pixel frames via `clip_frames`, added in Phase 2H for X3D-S. An S3D adapter could implement this same interface without any change to it.
- `CaptioningAdapter.caption(detections: List[DetectionResult], action: ActionObservation) -> str` (`app/captioning/base.py`) — takes detections + the action result, returns a string. A BLIP-backed adapter would need the raw frame too, which this interface does **not** currently pass — see the integration plan below for the smallest change that would require.

## Part B — S3D feasibility: **PASS**

| Measurement | Value |
|---|---|
| torchvision S3D support | Yes — `torchvision.models.video.s3d` + `S3D_Weights.KINETICS400_V1`, no version issue |
| Weights download size | 33.5 MB (`s3d-d76dad2f.pth`, official `download.pytorch.org`) |
| Model load time (cold, incl. download) | 25.16s |
| Model load time (warm, cached) | 0.31–0.79s across 4 runs |
| Single-clip inference time (CPU, 16 frames, 224×224) | 0.91–1.91s across 5 runs |
| RSS before model load | 289.0 MB (Python + torch import baseline) |
| RSS after model load | 359.0 MB (**+70 MB**) |
| RSS after inference | 395.4 MB (**+106 MB from baseline**) |
| Test clip | `ai-service/datasets/webcam_staged_aggressive/webcam_staged_000.mp4` (real, local, already in the repo — 60 frames, 15fps, 640×480) |

**Top-5 predicted Kinetics-400 actions** (official `S3D_Weights.KINETICS400_V1.transforms()` preprocessing, 16 uniformly-sampled frames):

| Action | Score |
|---|---|
| baby waking up | 0.168 |
| crying | 0.083 |
| sneezing | 0.063 |
| eating burger | 0.053 |
| eating chips | 0.041 |

**Reported honestly, not softened**: this is a *staged-aggressive* test clip, and **none
of the top-5 predictions are remotely related to aggression or fighting** — all
confidences are low (max 0.17) and the top guesses are domestic/everyday actions.
Kinetics-400 itself has very few violence-specific classes to begin with (a
well-documented limitation of that benchmark for security use cases), so this is not
surprising, but it means S3D's out-of-the-box classification head is **not** a usable
violence/aggression signal as-is — its practical value here would be as a general
action-recognition backbone (replacing or supplementing the hand-written geometry
heuristic's label vocabulary) rather than a violence detector, and even then only after
a task-specific head is trained on top of it, exactly as this project's own Phase 2C
X3D-S work already did for a *different* backbone.

**CPU usability at low-frequency sampled-video cadence**: **yes, practically usable**.
At ~1-2s per 16-frame clip and a proposed low cadence (e.g. once every
`sequence_window_seconds` = 6s, matching the existing action-recognition cadence — the
same cadence X3D-S already runs at when enabled), inference cost is a small fraction of
the available time budget and well under the RAM budget. This mirrors the existing,
already-proven X3D-S integration pattern (Phase 2H) almost exactly — same order of
magnitude cost, on the same CPU.

## Part C — BLIP feasibility: **PASS, with a real memory caveat**

| Measurement | Value |
|---|---|
| transformers compatibility | Compatible once installed (was not installed at the start of this phase) |
| Weights download size | 989.8 MB (`pytorch_model.bin`) + tokenizer/config files — **946 MB** total in `~/.cache/huggingface` after download |
| Model load time (cold, incl. ~990MB download) | 617.96s (~10.3 min — dominated entirely by download bandwidth on this machine, not compute) |
| Model load time (warm, cached) | 7.70s |
| Caption inference time (CPU) | 1.94–4.03s across 2 runs |
| RSS before loading | 411.8 MB |
| RSS after model load | 621.5 MB (**+209.7 MB**) |
| **RSS after generating one caption** | **1,475.1 MB (+853.6 MB during generation alone)** |
| Test image | `ai-service/datasets/firearm_evaluation_v1/negative/neg_09_ordinary_portrait.jpg` (real, local, already in the repo) |

**Generated caption**: *"a woman in a white dress is standing in front of a mirror"*

Reported honestly: the actual image is a person standing in a plain room in a light
top — BLIP correctly identified a standing person and the general clothing tone, but
**invented a detail not present in the image** ("in front of a mirror" — there is no
mirror in this frame). This is a real, direct example of exactly the failure mode your
Part D principle warns against for the *existing* system's captions (never invent
objects not detected) — a genuine vision-language model does not automatically avoid
this; it has its own hallucination risk, of a different kind than the current
template's.

**Storage impact**: 946 MB (HF cache) + 113 MB (`transformers` package) + a smaller
amount for its transitive dependencies (tokenizers/safetensors/hf-xet, tens of MB) ≈
**roughly 1.1 GB added**, all still comfortably within the measured free space at every
point in this test.

**CPU/RAM usability**: workable but **the +853 MB spike during generation is the one
number worth flagging plainly for a 16GB machine already running two YOLO models, a
Node backend, and a browser** — it is not disqualifying on its own, but it means BLIP
should not run on every sampled frame; it is only sane at a low, event-triggered cadence
(e.g., once per alert or once per action-window evaluation), never per-frame.

**No smaller alternative was substituted** — BLIP-base loaded and ran successfully, so
Part C's fallback instruction ("if too slow or incompatible, propose the smallest
viable alternative") does not apply; it passed.

## Part D — Temporal next-event predictor: recommendation

### What's actually available to build from
- `CameraWindow.entries` (`app/common/frame_buffer.py`) — raw detections, pruned to 6s.
  **Too short-lived for "temporal history" in the sense of predicting a next *event*** —
  it's the input to the current-window action label, not a history of past labels.
- The backend `Action` table — **already has exactly the right shape of history**:
  `label`, `threatScoreHint`, `windowStart`, per camera, persisted every ~6s. This
  project already has **416 real historical rows for one camera** — genuine data, not
  hypothetical.

### Feasibility check performed (prototype only, not integrated)
Built an order-1 Markov transition table directly from the real `Action` history in
`database/dev.db`, then validated it **walk-forward** (each prediction uses only labels
that occurred strictly before it — no future data leakage):

```
Empirical transitions (excerpt):
  approaching        -> close_contact (3/3)
  close_contact      -> fighting_candidate (3/4), standing (1/4)
  standing           -> standing (220/287), walking (23/287), no_activity (22/287), weapon_detected (17/287), ...
  weapon_detected    -> standing (20/26), no_activity (3/26), walking (3/26)
```

**Walk-forward accuracy over the real 416-event sequence: 291/407 correct (71%)**,
versus a naive "predict next = current" baseline of **255/415 correct (61%)** on the
same data. The transition model genuinely uses sequence history and genuinely
outperforms just repeating the current label — this was measured, not assumed.

**Important caveat, disclosed**: a large share of this history is the scripted `/demo`
escalation sequence replayed several times (identical 5-step pattern at several
timestamps), plus one camera's data only. The 71%/61% comparison is real and correctly
computed, but reflects a dataset dominated by one repeated scripted pattern, not diverse
organic behavior — the honest expectation is that accuracy on genuinely varied future
footage would be lower than 71%, not that 71% is a general performance claim.

### Recommendation: smallest viable implementation
An **order-1 (or order-2 if time allows) Markov transition model**, structured exactly
like the project's other adapters:
- New `app/temporal_prediction/base.py` — a `TemporalPredictionAdapter` interface,
  `predict_next(history: List[ActionObservation]) -> PredictedEvent` (label + confidence
  + rationale string, mirroring `ActionObservation`'s own shape for consistency).
- New `app/temporal_prediction/markov_adapter.py` — maintains a transition-count table
  per camera (in-memory, bootstrapped from real historical `Action` rows already in the
  database at startup, then updated live as new actions are evaluated).
- Fully transparent and explainable (a literal frequency table), consistent with this
  project's existing `RuleBasedThreatEngine` philosophy — not a black box, and honestly
  labelable `mode="DEMO"` or a new `mode="REAL"` variant meaning "real frequency
  statistics, not a claim of forecasting accuracy" (same honesty pattern as every other
  adapter's `mode` field).
- **Not implemented in this phase**, per your instruction — this is a recommendation
  and a validated prototype only (see the throwaway script results above), not new
  production code.

This is realistically completable before Monday **as a small, isolated, well-tested
adapter behind its own interface** — it does not touch detection, action recognition,
captioning, or the threat engine, and can be demonstrated standalone (exactly as the
prototype above was) before any integration decision is made.

## Exact integration plan (if approved — not started)

1. `app/temporal_prediction/base.py` + `markov_adapter.py` (new files only).
2. `app/config.py` — one new setting, `temporal_prediction_adapter: str = "none"`
   (mirrors the existing `x3d_adapter` on/off pattern exactly — safe default, opt-in).
3. `app/services/pipeline.py` — a `get_temporal_predictor()` factory (mirrors
   `get_x3d_adapter()`), called *after* `evaluate_window()` produces its
   `ActionResult`, using the same lazy/fail-soft loading pattern already established.
4. If BLIP is approved as a captioning upgrade: `CaptioningAdapter.caption()`'s
   signature would need one additive, optional parameter (e.g. `frame: Optional[np.ndarray] = None`)
   since it currently has no access to pixels — the smallest possible interface change,
   backward-compatible with `TemplateCaptioner` (which would simply ignore the new
   parameter, exactly like `clip_frames` is already ignored by the geometry heuristic).
5. If S3D is approved as an action-recognition upgrade: no interface change needed at
   all — `clip_frames` already exists for this exact purpose (Phase 2H).
6. None of this is proposed to happen before Monday without your separate approval —
   this section documents *how*, not a commitment to *when*.

## Expected CPU/storage impact if all three were eventually enabled together

| | Approx. cost |
|---|---|
| Storage | ~1.1 GB (S3D 33.5MB + BLIP+deps ~1.06GB) — comfortably within the measured 12-17GB free |
| RAM, peak, if S3D and BLIP both ran in the same process at the same moment | ~400MB (S3D) + ~1.5GB (BLIP) + existing two YOLO models (~200-400MB combined, per earlier phases) ≈ **2.5-3GB working set** — fits in 16GB but is a real, non-trivial share of it, especially alongside Node/Chrome |
| CPU latency per cycle | S3D ~1-2s + BLIP ~2-4s, both far below the existing `sequence_window_seconds` (6s) cadence if run at that cadence, not per-frame |
| Markov predictor | Negligible (dictionary lookups) |

## Blockers

**None outright block either model.** The one real constraint worth flagging plainly:
BLIP's generation-time memory spike (+853MB) means it must run at a low, event-triggered
cadence, never per-frame — this is a design constraint for any future integration, not
a blocker to the feasibility conclusion.

## Summary

1. **S3D: PASS** — loads, runs, fast and light on this CPU; its stock classification
   head is not a usable violence signal on Kinetics-400's own vocabulary, matching the
   already-known limitation of generic action-recognition benchmarks for this domain.
2. **BLIP: PASS** — loads, runs, produces a coherent but sometimes-hallucinated
   caption; workable only at low cadence due to a real ~850MB generation-time RAM spike.
3. **Temporal predictor**: an order-1 Markov transition model over real historical
   Action data, validated (71% vs. 61% naive baseline, walk-forward, no data leakage) —
   smallest viable, realistically completable before Monday as an isolated adapter.
4. **Integration plan**: documented above, nothing started.
5. Waiting for approval before any production change.
