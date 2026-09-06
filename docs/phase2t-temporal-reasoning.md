# Phase 2T — Temporal Threat Escalation & Next-Event Reasoning

**Status: implemented, tested (26 new/updated tests, all passing), verified live.**
Prediction is surfaced as explainable context; it is architecturally incapable of
raising `threat_score` on its own — proven by construction (call ordering) and by a
dedicated adversarial isolation test. Firearm detector untouched and re-verified.

## 0. Verification before editing (as required — nothing assumed)

Re-read fresh before writing any Phase 2T code: `MarkovTemporalPredictor` /
`TemporalPredictionAdapter` (Phase 2R), `ActionResult`/`temporal_prediction` schema
field (Phase 2R), `pipeline.py`'s `evaluate_window()` / `maybe_predict_temporal()` /
`evaluate_weapon_detection()`, `CameraWindow` and its two persistence-counting methods,
current action/state labels (`demo_heuristic.py`'s `BASE_SCORE_BY_ACTION` keys), the
Phase 2S knife-floor logic in `rule_based.py`, and the existing temporal/threat test
files. Nothing from prior phase *reports* was taken on faith — e.g. the exact wording
of Phase 2S's knife-floor rationale string was re-read from `rule_based.py`, not
recalled.

## 1. Exact files changed

- `app/temporal_prediction/base.py` — added `PredictionOutcome` dataclass; changed
  `TemporalPredictionAdapter.observe()`'s return type from `None` to
  `Optional[PredictionOutcome]`.
- `app/temporal_prediction/markov_adapter.py` — `MarkovTemporalPredictor` now tracks one
  pending (predicted_label, confidence) tuple per camera; `predict_next()` stashes it
  (in every branch, including cold-start); `observe()` pops it and returns a
  `PredictionOutcome` comparing it against the label actually observed.
- `app/services/pipeline.py` — `maybe_predict_temporal()` now captures `observe()`'s
  return value and includes it as `previous_prediction_outcome` in the returned dict;
  `evaluate_window()` appends one sentence of temporal context to `rationale` (never to
  `threat_score`) when a prediction exists, placed *after* `threat_score` is already
  finalized.
- `app/tests/test_temporal_predictor.py` — 6 new unit tests for the prediction/outcome
  mechanism (9 pre-existing Phase 2R tests untouched).
- `app/tests/test_temporal_reasoning_pipeline.py` — new file, 11 pipeline-level tests
  (grounded/ungrounded transitions, explainable phrasing, prediction-is-not-proof
  isolation, outcome surfacing, knife-pathway and firearm-isolation regression).
- `scripts/evaluate_phase2t_temporal_walkforward.py` — new script; walk-forward
  validation of the *production* `MarkovTemporalPredictor` against real historical
  `Action` rows in `database/dev.db`.
- No changes anywhere in the firearm path, BLIP, S3D, X3D, detection, or backend/
  frontend/video-processing code.

## 2. Exact temporal logic changed

Order-1 Markov transition counting itself (Phase 2R) is **unchanged** — same per-camera
`from_label -> Counter[to_label]` frequency table, same "most frequent successor wins"
prediction rule. What Phase 2T adds is purely a *validation/observability* layer on top:

1. Every `predict_next(camera_id)` call now remembers what it predicted (even "nothing,
   cold start" as `(None, 0.0)`) before returning.
2. The *next* `observe(camera_id, label, ts)` call for that camera pops that pending
   prediction and reports whether `label` matched it (`True`/`False`), or `None` if
   nothing had actually been predicted (cold start / no successor yet — no judgment is
   possible, so none is made).
3. `evaluate_window()` surfaces this on `ActionResult.temporal_prediction` and appends a
   plain-language, explicitly-hedged sentence to `rationale` — **and does this after**
   `threat_score` has already been computed and returned by `RuleBasedThreatEngine.assess()`,
   so there is no code path by which the prediction can feed back into the score.

## 3. How leakage was prevented

Unchanged from Phase 2Q/2R's own guarantee, re-verified this phase:
`predict_next(camera_id)` reads only `self._last_label[camera_id]` and
`self._transitions[camera_id]` as they stand *before* the current event is recorded.
`evaluate_window()` calls `predict_next()` strictly before `observe()` within
`maybe_predict_temporal()` — confirmed by `test_predict_next_does_not_see_a_transition_before_it_is_observed`
(unit) and by the walk-forward script itself, which calls `predict_next()` then
`observe()` in that exact order for every historical row, so every accuracy number
below reflects only information available strictly before the event it predicts.

## 4. Historical walk-forward result (real data, production adapter)

`scripts/evaluate_phase2t_temporal_walkforward.py`, run against the single busiest real
camera in `database/dev.db` (495 real `Action` rows spanning
`['approaching','close_contact','fighting_candidate','no_activity','running','standing','walking','weapon_detected']`):

```
Walk-forward accuracy (production MarkovTemporalPredictor, no leakage):
  346/486 correct (71%) where a prediction was possible
  (9 cold-start/no-successor-yet cases had no prediction to judge)
```

This reproduces Phase 2Q's prototype-script number (71%) on the actual production
class, on a larger slice of real data — it is **not** a new, independently-higher
result, and is not claimed as one.

## 5. Naive baseline comparison

```
Naive "predict next = current" baseline, same sequence:
  302/494 correct (61%)
```

The Markov predictor beats the trivial baseline by 10 points on this sequence. As
stated in `markov_adapter.py`'s own docstring (unchanged this phase): this sequence is
dominated by one camera's own repeated behavior and **is not a generalization
estimate**.

## 6. Prediction → outcome validation result

Computed two independent ways over the same replay — via `observe()`'s own return
value (cross-checking #4's accuracy count) and via a direct total:

```
matched:      346
mismatched:   140
no judgment (prior prediction had no label): 9
match rate where a judgment was possible: 346/486 (71%)
```

This matches #4 exactly (346/486), which is expected — they are two views of the same
prediction stream — and is reported here as a **cross-check that the outcome-tracking
mechanism itself is counting correctly**, not as a second, independent accuracy claim.

Worked example, format as requested:

```
t1: current=approaching,  prediction=close_contact(1.00)         [3/3 in real data]
t2: actual=close_contact                                          -> matched
```

(`approaching -> close_contact` is 3/3 in the real data — see #7.)

## 7. Honest check of the "escalation story" transitions

Per the instruction to verify real data before testing a transition, not invent one
that "sounds good":

```
walking -> approaching:          0/45 (0%)   -- NOT supported by the real data
approaching -> close_contact:    3/3  (100%) -- supported
close_contact -> fighting_candidate: 3/4 (75%) -- supported
```

**This is reported as a limitation, not smoothed over.** The pipeline-level tests
(`test_approaching_to_close_contact_is_a_real_grounded_transition`,
`test_close_contact_to_fighting_candidate_is_a_real_grounded_transition`) use only the
two transitions the data actually supports, and a dedicated negative test
(`test_walking_to_approaching_is_honestly_not_predicted_because_data_does_not_support_it`)
confirms the predictor does not invent `walking -> approaching` for a fresh camera that
was never taught it either — it says "no prediction," not a guess.

## 8. Real live temporal result (Test A — normal static scene)

15 real frames of a real, calm single-person photograph POSTed to a fresh test camera
via `/infer/frame`, exactly as `video-processing` would. Final `/infer/sequence` read:

```
label: standing
threat_score: 0.05
rationale: "base risk for 'standing' = 0.05 = 0.05. Temporal context: current action
  is 'standing'; model predicts 'standing' next (confidence 1.00, based on 6 prior
  observations for this camera)."
temporal_prediction.previous_prediction_outcome: predicted=standing, actual=standing,
  matched=true
```

A static scene predicting more of the same, at 100% confidence, with `threat_score`
completely unaffected — exactly the undramatic result the task said was "perfectly
acceptable," not manufactured into something more exciting.

**Unrelated observation, reported for transparency, not fixed (firearm is out of
scope):** the same "normal" test photograph also triggers the firearm detector at
~0.54 confidence, geometrically valid (80% of frame, under the 90% rejection filter).
No firearm alert was produced across all 15 frames despite the detection persisting the
whole time — consistent with the same BLIP-processing-delay effect on wall-clock
persistence timing that Phase 2S found and fixed *only* for the knife path (see
Limitation, below). This is evidence *of* the known limitation, not a new bug
introduced this phase, and firearm code/config was not touched to investigate or fix
it.

## 9. Real live knife result (Test B)

**Provenance note, stated plainly:** the specific image file used for Phase 2S's live
knife test was never persisted to disk (diagnostic capture only saves the `"firearm"`
class by default) and this session has no outbound access to fetch a substitute image
(verified: connections to external image hosts do not complete) and no live camera/user
is available right now to recapture one. Inventing detection numbers "because they
sound plausible" was explicitly ruled out. So this test replays the **exact real
confidence/bounding-box values** Camera 01 genuinely recorded from a real knife+person
appearance earlier the same day (`database/dev.db`, frameTimestamp
`1788610080357`/`1788610082890` — not rounded, not invented) through the current,
temporal-predictor-enabled pipeline code, using current wall-clock timestamps so
persistence/temporal logic runs exactly as for a fresh frame. Stage 1 (YOLO) itself was
not re-run; everything from buffering onward (persistence check, action recognition,
temporal prediction, threat assessment, real backend delivery) ran for real against the
live backend.

```
Evaluation 1: label=standing, threat_score=0.45
  rationale: "...knife detected (persisted) + person present -> raised to 0.45..."
  temporal_prediction: predicted_label=None (cold start — honest, not manufactured)
  previous_prediction_outcome: matched=None (nothing was predicted yet)

Evaluation 2: label=standing, threat_score=0.50
  rationale: "...raised to 0.45 + sustained/rising activity across recent windows
    (+0.05) = 0.50..." (the +0.05 is pre-existing Phase 2P/2S logic, not new)
  temporal_prediction: predicted_label=None ("standing" has no recorded successor yet)
```

The Phase 2S floor (0.45, MEDIUM) fired correctly on real detection values, and its
value/rationale text is byte-identical in shape to Phase 2S's own — the temporal
predictor never had a prediction to offer in this short a sequence, and the floor was
computed with or without it exactly the same way. This is a *weaker* live demonstration
of "prediction does not affect the knife floor" than the dedicated adversarial unit test
below, which forces the interesting case.

## 10. Whether temporal prediction affected threat scoring — and exactly how

**It did not, anywhere, by construction — not just by observation.**
`evaluate_window()` calls `get_threat_adapter().assess(...)` and finalizes
`threat_score`/`rationale` *before* `maybe_run_s3d()` or `maybe_predict_temporal()` are
even invoked (see `pipeline.py`). The temporal-context sentence is string-concatenated
onto the already-final `rationale` afterward; `threat_score` is never reassigned.
Proven adversarially by `test_a_fighting_candidate_prediction_alone_does_not_raise_the_score`:
a predictor primed to predict `fighting_candidate` at 100% confidence is attached to a
calm, single-person window — `threat_score` stays exactly `0.05`, and the prediction is
still visible in `temporal_prediction`/`rationale`, phrased as a prediction
("model predicts 'fighting_candidate'"), never as an observed fact. A second test
(`test_firearm_path_unaffected_by_temporal_predictor`) confirms the same adversarial
priming has zero effect on `evaluate_weapon_detection()` — its rationale contains
neither `"temporal"` nor `"predict"` at all, because `ActionObservation` on that path
never carries a `metrics` key the temporal code reads.

## 11. Alert/incident/WebSocket/DB evidence

Test A (normal scene): 5 real `Action` rows, all `label=standing`,
`threatScoreHint=0.05`; zero `Alert` rows — correctly no alert for a low-risk scene.

Test B (knife): real `Detection` rows for both `knife` and `person`; 2 real `Action`
rows (`threatScoreHint` 0.45, then 0.50); **2 real `Alert` rows**, both
`severity=MEDIUM`, `threatScore` 0.45/0.50, `status=NEW`. WebSocket listener (real
client, real JWT) captured, for the Test B camera: 6 `detection.created`, 2
`action.detected`, 2 `alert.created` events. No `Incident` was auto-created for a
MEDIUM alert — pre-existing backend behavior, not a Phase 2T change.

Both test cameras were deleted afterward via the real backend API (cascade delete).
Database counts before Phase 2T's live testing and after cleanup are **identical**:
`Camera=1, Detection=1414, Action=495, Alert=42, Incident=32`.

## 12. Firearm code/config/model — confirmed unchanged

- `models/firearm_yolov8n.pt` MD5: `a03b0c5aee7ad426fafd7265fa77ba5d` (matches baseline).
- `ai-service/.env`: only `WEAPON_ADAPTER=yolov8_firearm` present — no other
  firearm/weapon override lines.
- `app/config.py` defaults, re-checked: `firearm_confidence_threshold=0.5`,
  `firearm_max_bbox_area_ratio=0.9`, `firearm_persistence_min_hits=2`,
  `firearm_persistence_window_seconds=4`, `weapon_alert_cooldown_seconds=15` — all
  match baseline.
- `evaluate_weapon_detection()` and `CameraWindow.count_recent_frames_with_object()` in
  `pipeline.py`/`frame_buffer.py` were re-read this phase and are byte-identical to
  Phase 2S; `ActionObservation` on the firearm path never carries `knife_persisted` or
  any temporal-prediction-derived field, so the new logic is structurally inert for it
  — confirmed again by `test_firearm_path_unaffected_by_temporal_predictor`.

## 13. Complete regression result

Run after all live testing and cleanup:

```
ai-service:       178 passed
backend:            21 passed
frontend:           42 passed
video-processing:    6 passed
TOTAL:             247 / 247
```

No existing test was removed, skipped, or weakened to reach this number.

## 14. Remaining limitations (stated plainly, not smoothed over)

- **Firearm persistence timing (explicitly not fixed this phase, per instruction):**
  Firearm persistence may require a separate timing audit because downstream processing
  latency can affect wall-clock persistence semantics. The firearm path was
  intentionally left unchanged to preserve Phase 2L/2M evaluation comparability. (Test A
  above produced fresh, real evidence consistent with this exact effect — a persistent
  firearm-shaped detection across 15 frames did not alert — but no firearm code,
  config, or timing logic was touched to investigate or address it.)
- **`walking -> approaching` is not supported by the real historical data (0/45).** Any
  future work describing an "approach → escalate" temporal story should use
  `approaching -> close_contact` (3/3) and `close_contact -> fighting_candidate` (3/4)
  instead, or gather more data before relying on the `walking` starting point.
- **In-memory, per-process, no backend bootstrap (Phase 2R limitation, unchanged):** the
  Markov predictor's history resets on every `ai-service` restart and does not read the
  backend's persisted `Action` history to warm itself. It genuinely learns from live
  traffic within the process's uptime only.
- **Test B replayed real historical detection values rather than a fresh live image**
  (see §9) because the original Phase 2S capture was never saved to disk and no
  substitute image or live camera was available this session. The threat-assessment and
  temporal-prediction code that ran was 100% real and unmodified; only Stage-1 YOLO
  inference itself was not freshly re-run.
- **71%/61% remains a single-sequence, single-camera prototype-scale validation
  result**, not a claim of general-purpose next-action forecasting accuracy — restated
  here exactly as Phase 2Q/2R required, because the underlying adapter and its
  validation methodology did not change this phase.
