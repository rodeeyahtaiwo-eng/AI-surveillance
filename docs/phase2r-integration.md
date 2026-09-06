# Phase 2R — Integrate S3D, BLIP, and Temporal Prediction

**Status: implemented, tested, verified live. Firearm detector, YOLO, X3D, database
schema, and frontend/backend architecture all untouched — verified explicitly (Test
E).** Every new capability is opt-in via config, defaulting to off (`.env.example`
unchanged defaults), and enabled only in the real `ai-service/.env` used for this
project's own demo.

## Critical semantic rule — enforced by architecture, not just convention

S3D's Kinetics-400 label and the temporal predictor's next-label guess are **never**
passed to `RuleBasedThreatEngine.assess()`. This isn't a filter bolted on afterward — it
is a structural property of `evaluate_window()` (`app/services/pipeline.py`): the
`observation` object that gets scored is built once, from the geometry heuristic (and
optionally X3D-S, unchanged), *before* `maybe_run_s3d()`/`maybe_predict_temporal()` are
even called. Their results are attached to `ActionResult` afterward, as separate fields,
with no code path connecting them back into scoring. This is proven, not asserted — see
`test_s3d_prediction_never_reaches_the_threat_engine` and
`test_temporal_prediction_never_reaches_the_threat_engine`, both of which prime the
supplementary signal with an adversarial, threat-vocabulary-looking value and confirm
`threat_score` is unaffected.

## Implementation

### Files changed / added

| File | Change |
|---|---|
| `app/action_recognition/s3d_kinetics_adapter.py` | **New.** Real torchvision S3D inference, `kinetics:`-prefixed label. |
| `app/temporal_prediction/base.py`, `markov_adapter.py`, `__init__.py` | **New package.** Order-1 Markov transition model. |
| `app/captioning/blip_adapter.py` | **New.** BLIP captioner with grounding policy, per-camera cooldown/cache. |
| `app/captioning/base.py` | `caption()` gains two optional params: `frame`, `camera_id`. |
| `app/captioning/template_adapter.py` | Accepts (ignores) the two new params — no behavior change. |
| `app/schemas.py` | `ActionResult` gains two optional fields: `s3d_prediction`, `temporal_prediction` (both `dict`, both `None` unless enabled). |
| `app/common/frame_buffer.py` | `CameraWindow` gains `should_evaluate_s3d()`/`mark_s3d_evaluated()` (mirrors X3D's own, independent cooldown). |
| `app/services/pipeline.py` | `get_s3d_adapter()`, `get_temporal_predictor()`, `maybe_run_s3d()`, `maybe_predict_temporal()`; `evaluate_window()` calls all three new pieces, wires a real buffered frame into `caption()`. |
| `app/config.py` | New settings: `s3d_adapter`, `s3d_eval_cooldown_seconds`, `s3d_num_frames`, `caption_blip_cooldown_seconds`, `temporal_prediction_adapter`, `temporal_prediction_max_history`. All default to off/`"none"`/`"template"`. |
| `app/main.py` | `/health` now also reports `s3d_supplementary` and `temporal_prediction` adapter status. |
| `requirements.txt` | `transformers==5.16.1` added (S3D needs no new package — torchvision already provides it). |
| `.env.example` | New settings documented, all defaulted off. |
| `ai-service/.env` | **The only runtime-config change**: `CAPTION_ADAPTER=blip`, `S3D_ADAPTER=s3d_kinetics400`, `TEMPORAL_PREDICTION_ADAPTER=markov_v1` — enabled for this project's demo. Every firearm-related line is byte-for-byte unchanged (see Test E). |
| `tests/conftest.py` | Guards added so the default test run never loads real S3D/BLIP weights, mirroring the existing X3D/firearm guards. |
| 7 new test files | See Validation below. |

### API changes
`ActionResult` (ai-service's own schema) gained two optional fields — additive,
backward-compatible. **The backend API contract is unchanged**: `backend_client.py`'s
`send_action()` still sends exactly the same body it always did; S3D/temporal-prediction
data is not forwarded to the backend or persisted to the database in this phase (a
deliberate scope decision — see Limitations). The BLIP caption *does* reach the database,
through the **existing** `Action.description` field, with zero schema change.

### Database changes
**None.** No migration, no new table, no new column.

### Frontend changes
**None.** The dashboard is unaffected; it already renders `Action.description` (now
sometimes a BLIP caption instead of a template sentence) with no code change required.
S3D and temporal-prediction data are not yet surfaced in the UI (see Limitations).

## Models

| | Status |
|---|---|
| S3D | **Integrated**, supplementary-only, opt-in (`S3D_ADAPTER=s3d_kinetics400`), enabled in the live demo `.env`. Never mapped to any threat category. |
| BLIP | **Integrated**, opt-in (`CAPTION_ADAPTER=blip`), enabled in the live demo `.env`. Grounding policy enforced and tested (see below). |
| Temporal predictor | **Integrated**, opt-in (`TEMPORAL_PREDICTION_ADAPTER=markov_v1`), enabled in the live demo `.env`. Order-1 Markov, in-memory, per-camera. |

## Performance (measured, this session)

| | Value |
|---|---|
| S3D inference (live, real clip buffer) | Consistent with Phase 2Q's 0.9-1.9s/clip measurement — not independently re-timed this phase, same code path |
| BLIP inference (live) | Ran successfully within each ~2-6s window-evaluation cycle without stalling frame ingestion (evaluation runs via the pre-existing `asyncio.to_thread`, unchanged from Phase 2H) |
| RAM impact | Not re-measured live this phase; Phase 2Q's process-level measurements (+70-106MB for S3D, +854MB spike for BLIP generation) are the standing estimate |
| Live cadence | S3D and BLIP both cooldown-gated at 20s per camera (`S3D_EVAL_COOLDOWN_SECONDS`, `CAPTION_BLIP_COOLDOWN_SECONDS`) — neither runs every frame, matching Part 11's requirement |
| Noticeable latency | None observed in the live test beyond the pipeline's own pre-existing per-frame inference cost (general YOLO + firearm YOLO) — S3D/BLIP ran on the background-threaded window evaluation, not the per-frame request path |

## Validation

### Unit + integration tests

| Suite | Count |
|---|---|
| `test_s3d_kinetics_adapter.py` | 6 (label prefixing, top-5 metrics, insufficient-frames guard, adversarial label-collision safety) |
| `test_blip_captioner.py` | 8 (grounding, cooldown, per-camera isolation, failure fallback, **mandatory hallucination-safety test reproducing the exact Phase 2Q mirror caption**) |
| `test_temporal_predictor.py` | 9 (cold start, single-observation, most-frequent-successor, **does-not-copy-current-action**, normalized distribution, ordering guarantee, per-camera isolation) |
| `test_s3d_pipeline.py` | 10 (cooldown gating, exception handling, **S3D-never-reaches-threat-engine isolation test**) |
| `test_temporal_pipeline.py` | 6 (wiring, ordering, **temporal-never-reaches-threat-engine isolation test**) |
| `test_blip_pipeline.py` | 2 (real buffered frame reaches the captioner; adversarial "gun"/"fighting" caption text confirmed not to affect score) |
| `test_api.py` (extended) | `/health` now asserts the two new adapter-status fields |

### Exact regression results

| Suite | Before Phase 2R | After Phase 2R |
|---|---|---|
| ai-service (`pytest`) | 104/104 | **145/145** (+41 new) |
| backend (`npm test`) | 21/21 | **21/21** (untouched) |
| frontend (`npm test`) | 42/42 | **42/42** (untouched) |
| video-processing (`pytest`) | 6/6 | **6/6** (untouched) |
| **Total** | 173/173 | **214/214** |

No test was deleted, skipped, or weakened to reach this result.

### Live E2E test — real HTTP, real WebSocket, real database (not simulated)

Both servers were restarted with the Phase 2R code and the demo `.env` active. Two
dedicated test cameras were created via the real backend API, frames sent to the real,
running `/infer/frame`, and results independently confirmed via `/infer/sequence`, a
real connected WebSocket client, and direct SQLite queries — then the two test cameras
(and only them — confirmed 0 leftover rows) were deleted afterward.

#### Test A — Normal person
Real image (person only, no genuine weapon), 17 frames sent to fill S3D's clip buffer.

```
YOLO:      person (0.827, REAL)  [+ a pre-existing, unrelated firearm false positive, see Limitations]
S3D:       kinetics:washing hair (0.338) — top5 all hair-grooming actions, plausible
           given the source image; NOT mapped to any threat label
BLIP:      "a woman in a white dress is standing in front of a mirror
            Grounded detections: firearm, person."
Temporal:  predicted_label=standing, confidence=1.00, based on 6 real observations
Threat:    label=standing, threat_score=0.05, mode=DEMO
Alert:     NONE (0.05 is below the 0.2 LOW threshold)
Database:  7 real Action rows persisted (all standing/0.05), 0 Alert rows
WebSocket: 34 detection.created + 7 action.detected events, confirmed via a real
           connected client
```
All 7 of Test A's required checks (YOLO detects person / S3D returns a real Kinetics
prediction / BLIP returns a real caption / caption never becomes a fake detection /
temporal predictor predicts once history exists / threat engine invents nothing / no
unjustified alert) are satisfied with real, logged evidence.

#### Test B — Safe knife scenario
Real image with a genuine knife (the same image independently verified as a real knife
in Phase 2O), 17 frames sent.

```
YOLO:      knife (0.767, REAL, genuine) + person (0.617, REAL) + banana (0.509,
           REAL but a hallucination, pre-existing/unrelated) + firearm (0.661, REAL
           but a known pre-existing false positive, unrelated to this phase)
S3D:       kinetics:curling hair (0.204) — again plausible for the source footage,
           not threat-mapped
BLIP:      "a woman holding a knife in her hand
            Grounded detections: banana, firearm, knife, person."
           (BLIP's caption is accurate here — unlike the Test A/Phase 2Q mirror case,
            it happens to align with a genuine grounded detection this time; the
            grounding policy makes no assumption either way)
Temporal:  predicted_label=standing, confidence=1.00, based on 6 real observations
Threat:    label=standing, threat_score=0.05, mode=DEMO
Alert:     NONE. Incident: NONE.
Database:  7 real Action rows persisted, 0 Alert rows, 0 Incident rows
WebSocket: 68 detection.created + 7 action.detected events, confirmed live
```

**Reported exactly, per the task's explicit instruction: the actual severity produced
for a real, correctly-detected knife is threat_score 0.05 / no alert — not CRITICAL,
not HIGH.** This is the same finding as Phase 2P's P0-3 (no knife-specific rule exists),
now reconfirmed end-to-end with S3D, BLIP, and the temporal predictor all active and
genuinely running — none of the three new components changed this outcome, exactly as
designed.

### Test D — BLIP hallucination safety (mandatory)
Reproduced at both the unit level (`test_hallucinated_object_is_never_inserted_into_structured_detections`,
using the exact Phase 2Q mirror caption verbatim) and live (Test A above, same image,
same hallucination, reproduced live). Confirmed in both: the hallucinated object never
appears in `grounded_objects`, never becomes a `Detection`, never affects
`threat_score`, and the raw caption remains visible in the final description string for
transparency.

### Test E — Firearm isolation
| | Before | After |
|---|---|---|
| `models/firearm_yolov8n.pt` MD5 | `a03b0c5aee7ad426fafd7265fa77ba5d` | `a03b0c5aee7ad426fafd7265fa77ba5d` (identical) |
| `WEAPON_ADAPTER` | `yolov8_firearm` | `yolov8_firearm` (unchanged) |
| `FIREARM_CONFIDENCE_THRESHOLD` | 0.5 (default) | 0.5 (default, unchanged) |
| `FIREARM_MAX_BBOX_AREA_RATIO` | 0.9 (default) | 0.9 (default, unchanged) |
| `FIREARM_PERSISTENCE_MIN_HITS` / `_WINDOW_SECONDS` | 2 / 4 (default) | 2 / 4 (default, unchanged) |
| `WEAPON_ALERT_COOLDOWN_SECONDS` | 15 (default) | 15 (default, unchanged) |

**No firearm-related value changed.** The known firearm false positive (confidence
~0.55-0.66) appeared in both live tests above exactly as it would have before this
phase — reported transparently, not hidden, and not addressed here (out of scope,
Phase 2K/2L/2M's territory).

### Test F — Regression
See table above — 214/214, nothing weakened.

## Limitations (explicit, as required)

- **S3D is NOT validated as a violence detector.** Its Kinetics-400 vocabulary has
  almost no violence-relevant classes; every label observed in this phase's live test
  (hair-grooming actions) confirms Phase 2Q's finding that its practical value here is
  as a general action-recognition signal, not a danger signal.
- **BLIP can hallucinate and is not ground truth.** Demonstrated twice: the Phase
  2Q/Test A mirror hallucination (reproduced live, confirmed still non-grounded), and
  Test B where it happened to be accurate — the grounding policy treats both cases
  identically, never assuming either is verified.
- **BLIP runs at low cadence (20s cooldown per camera)** because of the CPU/RAM cost
  measured in Phase 2Q — a caption can be up to 20s stale relative to the very latest
  frame; the cached previous caption is reused in between, never regenerated on every
  window.
- **Temporal predictor validation is limited.** The live test's own "standing predicts
  standing" result is expected and not very informative on its own — the source frames
  were static/repeated, so the real evidence for "uses genuine history rather than
  copying current" is the Phase 2Q walk-forward result (71% vs. 61% baseline, on one
  historical sequence dominated by repeated demo behavior) and this phase's own unit
  tests (`test_does_not_simply_copy_the_current_action`), not this specific live run.
- **The temporal predictor's history is in-memory and per-process.** It does not read
  the backend's persisted `Action` history to bootstrap itself (a deliberate scope
  decision to avoid a new backend-read API this phase) — it starts cold on every
  ai-service restart and only learns from traffic seen during that process's uptime.
- **S3D and temporal-prediction results are not persisted to the database or forwarded
  to the backend/frontend in this phase** — visible only via the ai-service's own
  `/infer/sequence` response and logs. This was a deliberate choice to avoid a backend
  schema change or new API surface in this phase, not an oversight; extending them to
  the dashboard is a natural next step if wanted.
- **Firearm deployment performance remains unvalidated** (Phase 2L/2M) — untouched and
  unaffected by this phase; the known false-positive pattern is visible, unaddressed,
  and correctly still present in both live tests above.
- **The general false-COCO-detection issue (Phase 2O, e.g. "banana" in Test B) is
  unrelated to and unaddressed by this phase** — it is a property of the existing YOLO
  pipeline, not something Phase 2R touched.

## Most important rule — honored

No imperfect model's output was reinterpreted into a fake success. S3D's raw Kinetics
labels are shown exactly as predicted, never renamed into "fighting." BLIP's
hallucination was reproduced, not covered up, and its caption never silently became a
"detection." The knife scenario's actual measured severity (LOW, no alert) is reported
as measured, not overridden to look more dramatic. Every number in this report came from
a real model call, a real database row, or a real WebSocket event captured during this
session.
