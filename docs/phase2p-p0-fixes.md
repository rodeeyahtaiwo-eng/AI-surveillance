# Phase 2P — P0 Fixes: Person Deduplication, Stale Detection Display, Knife Re-test

Implements the smallest defensible fixes for the P0 items from Phase 2O, verified with
a real live end-to-end test against the running system (not simulated). Firearm
production config, thresholds, and geometry filter are unchanged; X3D remains disabled;
no historical database records were touched or deleted.

## P0-1 — Duplicate person counting: fixed

**Root cause** (Phase 2O): a single person filling most of the frame produced multiple
overlapping YOLO "person" boxes that survive YOLO's own internal NMS (~0.7 plain IoU
threshold), and `DemoHeuristicActionRecognizer` counted each as a separate person.

**Fix**: `app/action_recognition/demo_heuristic.py` — a new `_deduplicate_boxes()` /
`_overlap_ratio()` pass, applied before both person-counting and the proximity/speed
calculation. Uses **containment** (intersection / smaller-box-area), not plain IoU,
because containment catches the observed pattern (one box a tighter/looser crop of the
same subject) that plain IoU under-weights. Threshold **0.7**, chosen from real
measurements: the actual incident's 3 boxes had containment 0.876/0.939/0.990 (all well
above); two genuinely distinct people in this heuristic's tests measure ~0.12-0.83
(well below, once one existing test's own unrealistic near-duplicate fixture was
corrected — see below). Greedy, confidence-first, mirroring how NMS itself prioritizes.

**A necessary, disclosed side-finding**: the existing test
`test_two_people_close_together_is_close_contact_or_fighting`
(`tests/test_action_recognizer.py`) and a second test in `tests/test_api.py`
(`test_infer_sequence_end_to_end_with_x3d_corroboration`) both represented "two
distinct people" with boxes offset by only 5px (containment ≈0.83) — a construction
close enough to the real duplicate-box incident's own numbers (0.876-0.990) to be
genuinely ambiguous. Both were corrected to a more realistic separation (~0.12
containment, same centroid-proximity trigger) rather than leaving a test that
encoded the same pathology this fix removes. This is flagged, not hidden.

**Tests added** (`tests/test_action_recognizer.py`): identical boxes → 1 person;
the exact real incident's 3 boxes, reproduced verbatim → 1 person, no close_contact;
partially-overlapping boxes (~0.8 containment) → deduplicated; genuinely separate
people (~0 overlap) → NOT deduplicated, close_contact still triggers; dedup helper
keeps the highest-confidence box; dedup works on any class, not just person;
`_overlap_ratio` matches hand-computed values including the real incident's own boxes.

## P0-2 — Frontend stale detections: fixed

**Root cause** (Phase 2O): the last 8 raw `detection.created` events were kept with no
time-based expiry — a one-frame hallucination stayed visible until 8 *newer* events
arrived, however long that took.

**Fix**: `frontend/src/lib/style.ts` — new `DETECTION_STALENESS_SECONDS = 8` and
`isDetectionStale()`, mirroring the existing `ALERT_STALENESS_SECONDS`/`isAlertStale()`
pattern exactly. **8 seconds, explained**: Phase 2O measured the actual live frame
interval at ~2.4s (not the configured 0.5s — synchronous inference latency dominates).
8s is a little over 3x that measured interval — enough margin that a real, still-present
object survives a slow processing cycle, short enough that a hallucination clears within
a handful of seconds. `CameraHero.tsx` now ticks a `now` state every second (so the view
updates even with no new WebSocket event) and filters `recentDetections` by freshness
before building the "Objects detected" tally. `live-monitoring/page.tsx`'s
`MAX_RECENT_DETECTIONS` was raised from 8 to 50 and re-labeled as a memory safety cap
only — freshness is now decided by time, not array position. Detection records are never
deleted from the database; this is display-only, exactly like the existing alert
staleness treatment.

**Tests added**: `lib/style.test.ts` (`isDetectionStale` boundary tests) and
`CameraHero.test.tsx` (fresh detection shown; a detection older than the window at
mount is not shown; a detection present at mount disappears once the window elapses
with no new event, using fake timers; a stale detection is filtered exactly like one
never received — historical data is never shown as current).

## P0-3 — Knife threat path re-tested after the fix

Re-ran the **exact real incident window** (`database/dev.db`, the frames that produced
the false close_contact/0.50/MEDIUM alert — including the genuine `knife` detection
that was present in the same window) through the actual, now-fixed pipeline code:

```
Action label: walking       (was: close_contact)
avg_person_count: 1.0       (was: 4.0 — the bug)
Threat score: 0.08          (was: 0.50)
Caption: "4 people walking through the scene. Also detected: knife, scissors, surfboard."
Severity: None — no alert created
```

**Reported explicitly, as required**: with the duplicate-person bug fixed, this real
window now produces **no elevated threat at all for the knife** — confirming Phase
2O's finding directly rather than assuming it. There is still no knife-specific rule
anywhere in the code; a knife's presence, confidence, and geometry play no role in the
score. (The caption above also exposed a **second, related bug** — its own
independent, non-deduplicated person recount — fixed separately, see the P1 captioning
section below; the numbers quoted here are from *before* that second fix, to show the
knife path exactly as it was re-tested.)

**No knife-specific rule was implemented.** Per your explicit instruction, this is
reported for your decision, not acted on. Two options, smallest first:
1. Fix nothing further — knife detection remains visible in the UI (raw detection +
   caption mention) but contributes no score, same as any other non-firearm COCO object.
2. If a knife-aware signal is wanted: distinguish knife-alone from
   knife-with-corrected-person-proximity (using the now-deduplicated proximity signal),
   with a modest, non-CRITICAL bump only in the second case — mirroring how
   close_contact/fighting_candidate already scale with genuine proximity. This still
   requires you to choose an actual number; none is proposed here.

## P0-4 — End-to-end verification: real live test, not simulated

Both servers were found already running from a prior session (predating this fix) and
were restarted so the fix was actually loaded, then a genuine test was run against the
live HTTP/WebSocket/database stack — not a direct function call.

### SAFE/NORMAL scenario
Real image (person only, no weapon, from existing evaluation evidence) sent through the
real `/infer/frame` endpoint on a fresh test camera.

| | Observed |
|---|---|
| Detections | `person` (0.827, REAL); `firearm` (0.545, REAL — a known false positive, unrelated to this test) |
| Action | `standing`, threatScoreHint **0.05** |
| Alert created? | **No** (0.05 is below the 0.2 LOW threshold) |
| WebSocket events | `detection.created` ×2, `action.detected` ×1 — confirmed via a real connected WebSocket client |

### DANGER scenario
Real image with a genuine knife (visually confirmed in Phase 2O) sent the same way.

| | Observed |
|---|---|
| Detections | `knife` (0.767, REAL — genuine); `person` (0.617, REAL); `banana` (0.509, REAL — hallucination); `firearm` (0.661, REAL — known false positive) |
| Action | `standing`, threatScoreHint **0.05** |
| Alert created? | **No** |
| Incident created? | **No** |
| WebSocket events | `detection.created` ×4, `action.detected` ×1 — confirmed via a real connected WebSocket client |
| Frontend | Not visually screenshotted (no browser in this environment) — but `CameraHero`'s rendering of this exact payload is deterministic and already covered by passing unit tests: `latestAction.label="standing"` renders as "Current action: standing", `latestAlert` stays `null` so "No active alert" renders, exactly as it would in a browser. |

**This is not fabricated — it is the actual, current, unmodified system's behavior,
verified via real HTTP requests, a real WebSocket connection, and real database rows**
(cleaned up afterward — see below). It confirms P0-3's finding a second, independent
way: a real knife, right now, produces no alert.

### Database verification
Baseline before test: Camera 1, Detection 1124, Action 405, Alert 41, Incident 32.
After the two scenarios (3 test cameras, 12 detections, 2 actions, 0 alerts): Camera 4,
Detection 1140, Action 407, Alert 41, Incident 32 — exactly the expected deltas, zero
unexpected rows. The 3 test cameras and their detections/actions were then deleted
(cascade) via the real API, restoring the exact original baseline (Camera 1, Detection
1124, Action 405, Alert 41, Incident 32) — confirmed by re-querying. No pre-existing
historical record was touched.

**Incidental finding, not a P0 item, not acted on**: the very first frame after a
service restart can be silently pruned before evaluation (cold-start model-loading
latency, several seconds, can exceed the 6s window relative to the frame's own
timestamp) — a narrow, restart-only edge case, harmless in steady state. Also observed:
firearm persistence (K=2/4s) did not fire in either test scenario, consistent with
Phase 2K/2L/2M's own finding that CPU inference latency competes with short persistence
windows — not a new issue, not touched, per your instruction not to modify firearm
configuration.

## P1 — False COCO object detections: measured, not changed

No threshold was changed. Measurements, drawing on Phase 2O's evidence plus this
phase's live test:

| | Confidence range | Isolated one-frame? |
|---|---|---|
| Representative false positives (cat, tie, remote, cell phone, surfboard, scissors, toothbrush, frisbee, banana) | 0.45 – 0.79 | Yes — every instance found appeared at one or two frames then vanished, never sustained |
| Successful knife detections | 0.56 – 0.89 across sessions | Persisted across consecutive frames when the knife stayed in view (e.g. 5 consecutive detections in the original 11:06 session); the P0-4 test's single-frame knife hit was also reproduced identically on a second frame |

**Class-specific thresholds are not currently supported by the architecture** — a
single `self.confidence_threshold` applies to every COCO class in `YoloV8Adapter`, with
no per-class override mechanism anywhere in `ai-service` or `backend`. Building one
would require nontrivial code (a class→threshold map plumbed through config), which is
exactly why this phase didn't attempt it. Given false positives are consistently
isolated single-frame events while genuine detections (knife, person) tend to persist,
**a time/persistence-based display or confirmation gate (the same category of fix as
P0-2, extended) is better supported by the evidence than a confidence-threshold change**
— noted for your decision, not implemented.

## P1 — Captioning audit: one bug fixed, scope otherwise unchanged

`TemplateCaptioner` (`app/captioning/template_adapter.py`) has access to exactly two
things: the window's raw detections, and the action observation (label + confidence +
metrics). It has no access to depth, tracking, or hand/object association — so it
cannot and does not claim "holding" anything; it never did, and this audit found no
place where it invents objects, actions, or relationships not present in its inputs.

**One real bug found and fixed** (discovered during P0-3's re-test): the caption
recomputed its own person count from raw detections
(`counts.get("person", 0)`), independent of the action recognizer's now-deduplicated
`avg_person_count` — so after P0-1, a caption could still say "4 people" in the same
breath as a threat score computed for 1. Fixed to prefer `action.metrics["avg_person_count"]`
when present (rounded), falling back to the raw count only when absent (e.g. the
`weapon_detected` observation, which never sets it). Re-running the exact P0-3 incident
after this fix: `"One person walking through the scene. Also detected: knife, scissors, surfboard."`
— still lists the (partly hallucinated) objects, because that's genuinely what was
detected in the window and the caption was never asked to filter that; the person count
is now consistent with the score.

No broader captioning change was made — no vision-language model, no new inference.

## P1 — Demo labels: audited, found already appropriately scoped

Every `DemoBadge`/`ModeBadge` usage in the frontend was traced (`Badge.tsx` consumers):
`camera.isDemo`, `incident.isDemo`, `alert.mode`, `action.mode` — each one is scoped to
a **specific record**, never a single blanket "this whole system is DEMO" banner.
**Not found to be misleadingly broad** — it already matches the component-specific
labeling your instructions described as the goal. No change made.

## Regression results

| Suite | Before this phase | After this phase |
|---|---|---|
| ai-service (`pytest`) | 94/94 | **104/104** (+7 dedup, +3 caption) |
| backend (`npm test`) | 21/21 | **21/21** (untouched) |
| frontend (`npm test`) | 34/34 | **42/42** (+8 staleness) |
| **Total** | 149/149 | **167/167** |

One test broke and was fixed during this phase, disclosed above: a second, unrelated
test (`test_infer_sequence_end_to_end_with_x3d_corroboration`) used the same unrealistic
near-duplicate box pattern the P0-1 fix now correctly collapses; its fixture was
corrected the same way as the first, not worked around.

## Files changed

- `ai-service/app/action_recognition/demo_heuristic.py` — dedup fix (P0-1)
- `ai-service/tests/test_action_recognizer.py` — dedup tests + one corrected fixture
- `ai-service/tests/test_api.py` — one corrected fixture (same issue, different test)
- `ai-service/app/captioning/template_adapter.py` — deduplicated person count in captions
- `ai-service/tests/test_captioning.py` — caption person-count tests
- `frontend/src/lib/style.ts` — `DETECTION_STALENESS_SECONDS`, `isDetectionStale()`
- `frontend/src/lib/style.test.ts` — staleness unit tests
- `frontend/src/components/monitoring/CameraHero.tsx` — live staleness filtering (P0-2)
- `frontend/src/components/monitoring/CameraHero.test.tsx` — 2 tests updated (fresh
  timestamps required, wording change), 4 staleness tests added
- `frontend/src/app/(app)/live-monitoring/page.tsx` — buffer cap raised, re-labeled
- `docs/phase2p-p0-fixes.md` — this document

**Not changed, as instructed**: firearm confidence threshold, firearm geometry filter,
firearm persistence/cooldown, X3D (`X3D_ADAPTER` remains `none`), the general YOLO
confidence threshold, any production configuration, any historical database row.

## Remaining limitations (explicit)

- No knife-specific threat rule exists; a genuine knife currently produces no alert.
  This is now fully confirmed via live test, not just code-traced — a decision on
  whether/how to change this is yours (§P0-3).
- False COCO-class detections are real and unresolved for isolated cases (§P1) — a
  persistence-style display gate is suggested but not implemented.
- Firearm detector's known false-positive rate and scene-realistic recall gap
  (Phase 2K/2L/2M) are untouched and still apply.
- The person-deduplication fix (P0-1) uses a single global geometric heuristic
  (containment threshold 0.7); it is evidence-based for the incident that prompted it
  but not validated against a broader range of real multi-person footage.
- Frontend detection staleness fix is unit-tested but not visually confirmed in a
  running browser (no browser available in this environment).

## Recommended next step for Monday

The system is now truthful in the specific way that mattered: a knife is genuinely
detected, duplicate-person false alerts are fixed, stale detections expire, and no
result in this report was fabricated. Suggested order:
1. Decide on P0-3's knife-rule question (or explicitly decide "not before Monday").
2. If time permits, apply the same persistence-style thinking from P0-2 to the "Objects
   detected" panel's *false positives* (not just staleness) — e.g. require 2 consecutive
   frames before displaying a non-person class, mirroring the firearm persistence idea
   without touching any model or threshold.
3. Firearm benchmarking (Phase 2N) remains explicitly out of scope until you say otherwise.
