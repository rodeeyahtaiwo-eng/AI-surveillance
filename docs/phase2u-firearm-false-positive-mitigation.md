# Phase 2U — Person-Relative Geometry Validation for Firearm Candidates

> **Superseded (Phase 2V)**: despite this mitigation, firearm detection has since been
> removed from the active runtime entirely — this phase's own finding that 45% of known
> false positives still became trusted events after mitigation was a direct input to
> that decision. See [`phase2v-firearm-removal.md`](phase2v-firearm-removal.md). This
> document (and the code it describes) is kept as the historical evaluation record.

**Status: implemented, tested (13 new tests, 260/260 total passing), evaluated against
198 real known-false-positive frames, 25 real genuine/replica firearm images, and the 2
real knife-as-"Gun" frames that motivated this phase.** Model, thresholds, persistence
config, and Phase 2T temporal prediction are all unchanged.

## 0. Correction to the prior audit (housekeeping, not part of the fix)

The last three audits reported a "stray ai-service process running under the wrong
Python interpreter" as an unresolved anomaly. It is not an anomaly: `pyvenv.cfg` shows
this venv was created with `home = C:\Python312`, and Python 3.12's Windows venv
`Scripts\python.exe` is a small **launcher stub**, not a full interpreter copy (270KB vs
the base interpreter's 104KB, different checksum) — it re-execs the base interpreter as
a child process while correctly redirecting `sys.path` to the venv's own
`Lib\site-packages`. This is standard CPython venv behavior on Windows, confirmed by
re-launching `ai-service` fresh this phase and observing the identical parent/child
pattern. **No code change addresses this because there is nothing to fix.** The earlier
"kill the stray process" recommendation is retracted.

## 1. The existing firearm detection path, traced

```
YoloV8FirearmAdapter.detect()        -- raw model inference, UNCHANGED
  -> geometry filter (firearm_max_bbox_area_ratio=0.9, in the adapter, UNCHANGED)
  -> DetectionResult(object="firearm", ...)
main.py: stored in CameraWindow.entries (raw, always, regardless of anything below)
  -> sent to backend as a Detection row (raw, always) -- UNCHANGED
main.py: evaluate_weapon_detection(camera_id, weapon_detections, concurrent_detections)
  -> **NEW (Phase 2U): person-relative geometry validation**
  -> count_recent_frames_with_plausible_firearm() (persistence, K=2/T=4s, UNCHANGED VALUES)
  -> should_alert_weapon() cooldown (UNCHANGED)
  -> RuleBasedThreatEngine.assess() (UNCHANGED) -> threat_score, rationale
  -> ActionResult("weapon_detected", ...) -> backend Action/Alert -> frontend
```

The exact place a firearm candidate can now be rejected, that did not exist before this
phase: immediately after Stage-1 detection, before it is allowed to count toward
persistence at all. Raw detection storage, the backend Detection row, and the frontend's
raw object list are **untouched** — a rejected candidate is still visible as evidence,
it simply cannot become a trusted `weapon_detected` event.

## 2. Baseline (before this phase's code change)

Both known knife frames, run through the unmodified pipeline:

| Frame | Raw `firearm` conf | BBox area ratio | Result before this phase |
|---|---|---|---|
| `20260905T163650132` (machete) | 0.744 | 0.896 | Passed the existing 0.9 geometry filter; would become a trusted `weapon_detected` event (threat_score 0.85, CRITICAL) once persistence (2 hits/4s) was met |
| `20260905T163732217` (knife+drink) | 0.758 | 0.771 | Same |

(In the actual live session that produced these two frames, persistence happened not to
be met, by under 1.1 seconds — see the prior audit. That was luck, not a guarantee.)

## 3. The validation rule chosen, and why

**Rule:** a firearm candidate is rejected if, in the same frame, a person is also
detected, AND the candidate's bounding box (a) has area ≥ the largest co-detected
person's own box area, AND (b) protrudes past that person's box edges by more than 5px
on at least one side. If no person is co-detected, the candidate is unaffected (falls
back to prior behavior).

**Why this rule, and not "reject large/centered boxes":** the task explicitly forbade
rejecting candidates merely for being large or centered, since the evidence doesn't
isolate that as *the* cause. This rule instead compares the candidate to a person
detected in the *same* frame — a physical-plausibility check (a handheld firearm should
be smaller than the person holding it), not a guess about the model's internal
behavior. It was checked against real evidence on both sides before being finalized:

| Case | Firearm/person area ratio | Protrudes past person box? | Rule outcome |
|---|---|---|---|
| Known FP 1 (machete) | 1.44 | Yes (both sides) | REJECTED |
| Known FP 2 (knife+drink) | 1.27 | Yes (left/right/top) | REJECTED |
| `ext_pos_07` (genuine-looking, person present) | 0.39 | — (area check fails first) | ACCEPTED |
| Rifle replica ×2 boxes (person present) | 0.57, 0.56 | — | ACCEPTED |
| `gettyimages` pistol (person present) | 0.60 | — | ACCEPTED |

Every genuine/replica firearm image locally available that also had a co-detected
person (3 of them — these are the *only* 3 local cases this rule can even apply to)
passes. The rule was tuned to separate exactly these real cases, not invented in the
abstract.

## 4. Implementation — exact files/functions changed

- `app/services/pipeline.py`: added `_firearm_candidate_is_plausible()` and the
  `FIREARM_VS_PERSON_AREA_RATIO` / `FIREARM_PROTRUSION_MARGIN_PX` constants; modified
  `evaluate_weapon_detection()` to accept an optional `concurrent_detections` parameter,
  filter `weapon_detections` through the new check before persistence, and use a new
  persistence-counting call.
- `app/common/frame_buffer.py`: added `CameraWindow.count_recent_frames_with_plausible_firearm()`
  — additive, takes the plausibility rule as a callable so this module stays
  detector-agnostic; does not modify or remove `count_recent_frames_with_object()`.
- `app/main.py`: captures `general_detections` (Stage-1 output) before it's merged with
  weapon detections, and passes it to `evaluate_weapon_detection()` as
  `concurrent_detections`.
- `tests/test_firearm_geometry_validation.py` (new, 13 tests).
- `scripts/evaluate_phase2u_firearm_geometry_validation.py` (new, evaluation script).

**Not changed:** `firearm_confidence_threshold` (0.5), `firearm_max_bbox_area_ratio`
(0.9), `firearm_persistence_min_hits` (2), `firearm_persistence_window_seconds` (4),
`weapon_alert_cooldown_seconds` (15), the firearm model file, the general YOLO model,
BLIP, S3D, Phase 2T temporal prediction, action recognition, captioning.

## 5. Evaluation results

**A. The two known knife frames:** both REJECTED at validation; would not become a
trusted event even if persistence were satisfied (confirmed via simulated sustained
appearance). Before this phase, both would have passed the geometry filter and could
become a CRITICAL alert given persistence.

**B. Full accumulated firearm-diagnostic-capture directory (198 real frames — grown
from Phase 2K's original n=45 through every subsequent phase's testing; no frame in
this directory has ever been confirmed to contain a real firearm):**
- 197/198 still produce a raw firearm detection ≥0.5 confidence (unchanged threshold —
  this phase does not touch detection itself).
- **109/197 (55%) are now rejected at the validation stage.**
- **88/197 (45%) are still accepted and would still become a trusted event.** This is
  not a claim of eliminating false positives — a substantial fraction remain, expected
  given the rule only fires when a person is co-detected in the same frame.

**C. Genuine/replica firearm images (25 local images, 16 with a raw firearm
detection):** only 3 also had a co-detected person (the only cases this rule can act
on) — **0/3 incorrectly rejected.**

**D. Normal/no-weapon scene:** the previously-documented false positive on the
"ordinary portrait" negative test image (0.545 confidence) is now REJECTED.

**E. Existing knife detection path:** untouched; `test_knife_threat_pipeline.py` (9
tests) unaffected, all passing.

## 6. What this does NOT prove

- It does not prove the firearm model now "understands" the difference between a knife
  and a gun — it has no such concept; this is a geometric plausibility filter applied
  after detection, not a change to the model's own reasoning.
- It does not eliminate false positives: 88 of 197 known-false-positive frames are
  still accepted (every case without a co-detected person is entirely unaffected, and
  even some with a person still pass if the box happens to be smaller than the person).
- It does not validate the rule against a large or diverse genuine-positive set — only
  3 local images had both a person and a firearm detection to test against.
- It does not change or improve persistence timing, BLIP, or the general detector's own
  false-positive rate (cat/toilet/etc.) — out of scope for this phase, unchanged.
- It is a plausibility heuristic, not a learned/validated model — its threshold (area
  ratio ≥ 1.0, 5px protrusion margin) was chosen from the available evidence, not
  cross-validated against held-out data (none exists locally).
