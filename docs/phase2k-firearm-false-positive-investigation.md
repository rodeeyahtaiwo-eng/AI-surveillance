# Phase 2K — Firearm False-Positive Investigation (post-persistence)

> **Superseded (Phase 2V)**: firearm detection has since been removed from the active
> runtime entirely — see [`phase2v-firearm-removal.md`](phase2v-firearm-removal.md).
> This document is kept as the historical evaluation record.

**Trigger**: despite Phase 2J's temporal-persistence gate (K=2 hits within 4s) already
being live, the firearm detector was still visibly flagging ordinary footage as
`firearm`. This phase does not assume persistence failed — it traces the full path,
inspects real evidence, and only then implements the smallest fix the evidence supports.

## 1. Path traced

`YoloV8FirearmAdapter.detect()` (`app/weapon/yolov8_firearm_adapter.py`) → merged into
`detections` alongside general YOLOv8 output (`app/main.py` `/infer/frame`) →
`window.add()` into the per-camera `CameraWindow.entries` buffer
(`app/common/frame_buffer.py`) → `evaluate_weapon_detection()`
(`app/services/pipeline.py`) checks `count_recent_frames_with_object("firearm", 4s) >= 2`
then `should_alert_weapon()` (15s cooldown) → `RuleBasedThreatEngine.assess()` (base score
0.85 for `weapon_detected`) → `backend_client.send_action()` → backend
`ingestAction()`/`evaluateAction()` (`threatEngine.service.ts`) → `scoreToSeverity()`
(CRITICAL at ≥0.85) → `Alert` + `Incident` rows created, `broadcast()` over WebSocket →
frontend `useRealtime` → `CameraHero`/Alerts/Incidents pages. Separately, *every* raw
detection (regardless of persistence) is also POSTed via `send_detections()` and shown in
the live "recent detections" feed, independent of whether an alert fires.

## 2. Classification of the current false positive

**Root cause: A — a genuine false positive from the firearm model itself**, not a
persistence bug, buffering/reuse bug, or frontend staleness bug. Each of B–E was checked
directly and ruled out:

- **B/C (persistence/buffering bug, stale detection reuse)**: `test_weapon_pipeline.py`'s
  existing 12 persistence tests pass unchanged, and manual tracing of `window.add()` /
  `count_recent_frames_with_object()` shows no old detection can be recounted — each
  `/infer/frame` call adds one fresh entry, `window.prune(6s)` evicts old ones every
  frame, and the persistence window (4s) is nested inside the prune window (6s) exactly
  as designed. No bug found.
- **E (backend alert lifecycle)**: querying `database/dev.db` directly shows **26
  `weapon_detected` CRITICAL alerts, all dated 2026-08-16 to 2026-08-19, zero since** —
  meaning persistence has correctly blocked every new alert since it went live; the 26
  historical ones predate it (this matches `docs/ai-pipeline.md`'s own note that a single
  frame "was previously enough, on its own, to fire a CRITICAL alert" before Option A).
  Those 26 rows are still sitting in the DB as `UNREVIEWED` — not a code bug, but a
  triage item: they inflate the Alerts/Incidents pages and analytics counts with weeks-old
  data. Out of scope for this fix; flagged for the user to review/dismiss.
- **D (frontend display artifact)**: `lib/style.ts`'s `isAlertStale`/
  `ALERT_STALENESS_SECONDS=120` and `CameraHero`'s "Historical alert" treatment were
  re-read and their tests re-run — working as designed. Irrelevant here anyway, since (E)
  shows no *new* alert has fired recently for this to be stale-displaying.
- **What's actually still happening today**: the raw **Detection** path (not the Alert
  path) is unaffected by persistence — every frame the model calls `firearm` is still
  POSTed to the backend and shown in the live detections feed. This is what the user is
  currently seeing, and it is confirmed live as recently as today.

## 3. Evidence used (diagnostic capture, database, real model re-run)

`DIAGNOSTIC_CAPTURE_ENABLED=true` was already on, and had already captured **45 real
`YoloV8FirearmAdapter` false-positive frames** (2026-08-19 and 2026-09-04 sessions) under
`ai-service/diagnostics/frames/firearm/`, each with confidence, bounding box, and
timestamp. `database/dev.db` independently confirms 64 real `firearm` `Detection` rows and
26 real `Alert`/`Incident` rows over the same period.

**Visual inspection of the captured frames** found no firearm in any of them:
- A hand holding a glass Coca-Cola bottle (confidence 0.63).
- A person's bare face/shoulders with no object at all (confidence 0.59).
- A person holding an elongated silver object (phone/hair-straightener) near their face
  in backlit conditions (confidence 0.845 — the highest ever captured).
- Several frames of a person's dark hair/head silhouette against a plain wall, at
  close range, with **no object present** (e.g. confidence 0.51, box `[4, 0, 640, 479]`
  on a 640×480 frame — i.e. the box is the entire frame).

**Bounding-box geometry, computed across all 45 real captures**: 36/45 (80%) had a box
covering more than 50% of the frame area; many exceeded 95–99%. This is the dominant,
identifiable pattern — the model is not localizing a small "Gun" region so much as
outputting a box spanning nearly the whole frame on ordinary close-up webcam
compositions (faces, hair, held objects), a plausible symptom of a model trained mostly
on cropped/isolated product-style firearm photos failing to generalize to
whole-scene surveillance framing.

## 4. Reproduction

Re-ran the **real, unmodified** `models/firearm_yolov8n.pt` (not a mock) against all 45
captured evidence frames:

| Check | Result |
|---|---|
| Frames re-evaluated | 45 |
| Frames the raw model still flags as `firearm` | 45/45 (all reproduce) |
| Frames flagged after the bounding-box filter (this fix) | 18/45 |
| Reduction | 27 frames eliminated (60%) |

Replaying the actual sequence through the **real** `evaluate_weapon_detection()` +
`CameraWindow` code (not a reimplementation), in original chronological order: **0 new
CRITICAL alerts before or after this fix** — confirming persistence is correctly
preventing new alerts today; the fix's effect is entirely on the raw detection/display
path and on any future sequence dense enough to satisfy persistence.

## 5. Threshold experiment (done, not just asserted)

| `FIREARM_CONFIDENCE_THRESHOLD` | False positives (of 45) still passing |
|---|---|
| 0.5 (current) | 45/45 |
| 0.6 | 28/45 |
| 0.7 | 12/45 |
| 0.8 | 1/45 |
| 0.85 | 0/45 |

Raising the threshold to 0.85 would have excluded every captured false positive — **but
the one manually-verified genuine detection on record (the model author's own example
image) scored 0.83** (`docs/ai-pipeline.md`). A threshold that excludes all known false
positives sits *above* the one confirmed genuine detection, with no margin — confidence
alone does not separate real firearms from these false positives in the available
evidence. **Threshold-raising was rejected as the fix** for this reason, not adopted.

## 6. Fix implemented

A bounding-box plausibility filter in `YoloV8FirearmAdapter.detect()`
(`app/weapon/yolov8_firearm_adapter.py`): a "Gun" detection whose box covers more than
`FIREARM_MAX_BBOX_AREA_RATIO` (default 0.9, i.e. 90% of the frame) of the original frame
area — read from ultralytics' own `Results.orig_shape`, not a resized/letterboxed
internal tensor — is discarded before it is ever returned, logged at `warning` level for
traceability. This runs *before* the detection reaches the frame buffer, persistence
count, backend ingestion, or the dashboard — so it suppresses the false positive
everywhere at once, not just at the alert gate.

0.9 was chosen as a physical-plausibility judgment (no handheld object should plausibly
fill 90%+ of a normal surveillance/webcam frame), not tuned against these 45 samples —
tightening it further to match this one person/room/session would be overfitting to a
non-representative sample. It is configurable (`FIREARM_MAX_BBOX_AREA_RATIO`) for future
adjustment as more evidence accumulates.

**What this fix does NOT do**: it does not touch the confidence threshold, the 0.85
`weapon_detected` base score, the persistence K/window, or the alert cooldown — all
verified unchanged by the full regression suite. It does not replace or retrain the
model.

## 7. Files changed

- `ai-service/app/config.py` — new `firearm_max_bbox_area_ratio` setting (default 0.9).
- `ai-service/app/weapon/yolov8_firearm_adapter.py` — the filter itself, plus a helper to
  read the original frame area from `Results.orig_shape`.
- `ai-service/tests/test_firearm_adapter.py` — `FakeResult` extended with `orig_shape`;
  6 new regression tests (discard near-whole-frame box, pass-through of a normal box,
  exact boundary behavior, mixed plausible/implausible boxes in one frame, graceful
  no-op when `orig_shape` is unavailable, and a pinned numeric fact about why the
  threshold experiment was rejected).
- `ai-service/.env.example` — documents `FIREARM_MAX_BBOX_AREA_RATIO`.
- `docs/ai-pipeline.md` — cross-reference to this document.
- `docs/phase2k-firearm-false-positive-investigation.md` — this document.

## 8. Tests before/after

- Targeted (`test_firearm_adapter.py` + `test_weapon_pipeline.py` + `test_weapon_adapter.py`):
  30/30 passing (24 pre-existing, unchanged + 6 new).
- Full `ai-service` suite: **88/88 passing before this change → 94/94 passing after**
  (verified by temporarily reverting the change and re-running, then restoring it).
- Full `backend` suite: 21/21 passing, unchanged (not touched by this fix).

## 9. False-positive results before/after

See §4 and §5 above — real-model re-run on real captured evidence: 45/45 → 18/45 frames
still flagged (60% reduction), 0 new alerts either way in this specific sequence (already
suppressed by persistence, independent of this fix).

## 10. New trade-offs

- The filter can, in principle, reject a genuine firearm detection if it is framed to
  fill nearly the entire camera view (e.g. an extreme close-up). This has not happened in
  any evidence collected so far (the only verified genuine detection, at 0.83 confidence,
  was not this project's own footage and its box geometry is not on record) — flagged as
  unvalidated, not claimed safe.
- 18/45 (40%) of known false positives are unaffected because their box size is
  plausible — the underlying model itself misclassifies ordinary objects (a bottle, a
  held straightener/phone, a face) as "Gun" at a normal box scale. This fix cannot and
  does not address that; it is a real, open limitation of the model, not hidden by this
  change.

## 11. What still remains unvalidated

- **The firearm detector's core accuracy is still not established** — it has never been
  run against a held-out set containing actual firearms in this project's own conditions.
  This phase adds more evidence of poor precision on ordinary footage; it does not add
  any evidence of the detector's true-positive rate.
- The 90% area-ratio cutoff is a plausibility judgment, not a validated parameter —
  there is no accuracy/precision/recall number to report for it beyond the 45-sample
  reduction above, and that sample is one person, one to two rooms, two sessions — not
  representative of deployment diversity.
- The 26 pre-existing `weapon_detected` CRITICAL alerts/incidents in `database/dev.db`
  (2026-08-16 to 2026-08-19) remain `UNREVIEWED` and are not addressed by this fix — they
  are historical, not reproducible under current code, but still visible in the
  Alerts/Incidents UI. Recommend the user reviews/dismisses them manually; no schema or
  UI change was made here since that was outside this investigation's scope.
- License and "research purposes only" caveats on the underlying checkpoint
  (`models/README.md`) are unchanged and still apply.
