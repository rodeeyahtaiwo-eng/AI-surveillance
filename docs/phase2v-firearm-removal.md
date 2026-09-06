# Phase 2V — Firearm Detection Removed From the Active Runtime

**Status: implemented.** Firearm/weapon detection has been deliberately removed as a
capability of this system. This is a scope reduction, not a bug fix — the goal is a
smaller, demonstrable system whose claims are actually supported by evidence, not a
larger list of unreliable ones.

## Why (evidence, not opinion)

Across Phases 2J–2U, `YoloV8FirearmAdapter` (a single-class "Gun" detector, fine-tuned
YOLOv8n) was built, temporally gated, geometrically filtered, and finally given a
dedicated person-relative geometry validation stage (Phase 2U) — and still did not
reach reliable firearm-vs-non-firearm discrimination:

- **Phase 2K/2L**: an unbiased sample of ordinary real webcam footage triggered a
  firearm detection roughly 1 in 4 frames, with no held firearm present.
- **Phase 2T's live audit**: two real, clearly-visible knife/machete frames were
  classified `"Gun"` at 0.744 and 0.758 confidence — both passed the existing
  bounding-box geometry filter (areas 89.6% and 77.1% of frame, under the 90% cutoff).
- **Phase 2U's own mitigation** (a physically-motivated check comparing a firearm
  candidate's box to a co-detected person's box) rejected both known knife
  false-positives and 55% of the full 198-frame accumulated known-false-positive set —
  but still left **45% of those known false positives** as trusted events. This was
  reported at the time as "not zero false positives," not as a solved problem.
- Checkpoint metadata for the model shows no evidence it was ever trained with knives,
  phones, or other everyday objects as explicit negative examples.

**What this is NOT saying**: this is not a claim that firearm detection is inherently
impossible, that the model "cannot detect guns," or that knives and firearms have now
been reliably distinguished from each other. It is a decision that the evidence
available for *this* detector, in *this* deployment, does not support shipping it as a
demonstrable capability.

## What was removed

Everything in the active runtime pipeline:

- `app/weapon/` (the entire package: `base.py`, `mock_adapter.py`,
  `yolov8_firearm_adapter.py`) — deleted.
- `app/services/pipeline.py`: `get_weapon_adapter()`, `detect_weapons()`,
  `evaluate_weapon_detection()`, and the Phase 2U `_firearm_candidate_is_plausible()` /
  `FIREARM_VS_PERSON_AREA_RATIO` / `FIREARM_PROTRUSION_MARGIN_PX` — removed.
- `app/common/frame_buffer.py`: `should_alert_weapon()`, `mark_weapon_alert()`,
  `last_weapon_alert_at`, `count_recent_frames_with_plausible_firearm()`, and the plain
  wall-clock `count_recent_frames_with_object()` (its only caller was the firearm path)
  — removed. `count_recent_frames_with_object_as_of()` — used by knife evidence — is
  **unchanged and fully intact**.
- `app/main.py`: Stage 1b (firearm detection call, its diagnostic capture, the
  detections merge, the urgent weapon-action evaluation) — removed. General detection
  (Stage 1) is untouched and is now the only detector in `/infer/frame`.
- `app/config.py`: `weapon_adapter`, `firearm_model_path`,
  `firearm_confidence_threshold`, `firearm_max_bbox_area_ratio`,
  `weapon_alert_cooldown_seconds`, `firearm_persistence_min_hits`,
  `firearm_persistence_window_seconds` — removed. `knife_persistence_min_hits` /
  `knife_persistence_window_seconds` — **unchanged**, still active.
- `app/threat/rule_based.py`: the `"weapon_detected": 0.85` entry in
  `BASE_SCORE_BY_ACTION` — removed (now falls through to the generic 0.1
  unknown-label default, matching any other string nothing in the pipeline produces).
  The knife-evidence floor logic (`KNIFE_*` constants, the `knife_persisted` check) —
  **entirely unchanged**.
- `.env` / `.env.example`: `WEAPON_ADAPTER` and all `FIREARM_*` / `WEAPON_*` lines —
  removed. `diagnostic_capture_classes` default changed from `"firearm"` to `"knife"`
  (a generic, class-agnostic mechanism — this only repoints its example default to the
  now-most-sensitive class, it was never firearm-specific code).
- `/health`'s `adapters` response — no longer reports a `"weapon"` key.
- Tests: `tests/test_weapon_pipeline.py`, `tests/test_weapon_adapter.py`,
  `tests/test_firearm_adapter.py`, `tests/test_firearm_geometry_validation.py` —
  deleted (they tested only the removed capability). Firearm-specific tests inside
  `test_api.py`, `test_threat_engine.py`, `test_knife_threat_pipeline.py`, and
  `test_temporal_reasoning_pipeline.py` — removed; every other test in those files is
  untouched. New tests added confirming the removal itself (see below).
- `scripts/evaluate_phase2u_firearm_geometry_validation.py` — deleted (it directly
  called the now-removed pipeline functions and had no continuing purpose once the
  capability it evaluated no longer exists).

## What was deliberately preserved

- **General object detection**, including the `knife` and `scissors` COCO classes —
  completely unchanged. `YoloV8Adapter` is untouched.
- **Knife threat-scoring path** (Phase 2S): persistence
  (`count_recent_frames_with_object_as_of`), the `KNIFE_WITH_PERSON_FLOOR` (0.45) /
  `KNIFE_WITH_AGGRESSIVE_CONTEXT_FLOOR` (0.70) logic in `rule_based.py` — byte-for-byte
  unchanged, re-verified by the existing (untouched) test suite in
  `test_knife_threat_pipeline.py`.
- **Action recognition** (`DemoHeuristicActionRecognizer`): standing/walking/
  running/close_contact/fighting_candidate/approaching, proximity and movement
  heuristics — untouched.
- **Captioning** (BLIP/template): untouched. `"Grounded detections:"` now simply never
  contains `firearm`, because nothing can produce that label any more — not because of
  any change to the captioning code itself.
- **Phase 2T temporal prediction**: untouched. The invariant that `threat_score` is
  finalized before temporal prediction is even computed (`pipeline.py`'s
  `evaluate_window()`) was re-verified after this change — see Regression below.
- **X3D-S / S3D supplementary signals**: untouched.
- `models/firearm_yolov8n.pt` — **kept on disk**, not deleted. It is still directly
  referenced by `scripts/evaluate_phase2l_firearm.py` and
  `scripts/evaluate_phase2m_firearm.py` (self-contained historical evaluation scripts
  that load it directly via `ultralytics.YOLO`, independent of the removed `app/weapon/`
  package) — per the removal criteria, a model still referenced by the evaluation
  system is not deleted. `models/yolov8n.pt` (general detector) is obviously untouched.
- Historical database records containing past firearm detections/alerts — untouched.
  This phase changes active detection capability going forward; it does not rewrite
  history.
- Historical docs (`phase2k`/`phase2l`/`phase2m`/`phase2u`) — kept as the evaluation
  record that justified this decision, each now carrying a note that the capability
  they discuss has since been removed.

## Regression

Ran the complete suite after the change: **[see final report for the exact numbers]**.
No test was deleted merely to make the suite pass — every removed test specifically
asserted behavior of the now-removed firearm capability; every other test is untouched
and still passes with its original assertions.

## Remaining limitations, stated plainly

- Firearm detection is not available in this system at all, in any form.
- This does not mean knife and firearm objects can now be reliably told apart — no
  detector in the active pipeline attempts that distinction; it means the previously
  unreliable firearm-specific detector is no longer running.
- The general detector's own `knife`/`scissors` real-world recall (found weak on
  certain hand-held presentations during the Phase 2T live audit) is unchanged by this
  phase — this was a pre-existing, separately-tracked limitation, not something this
  removal fixes or worsens.
- General-detector false positives on other COCO classes (`cat`, `toilet`, `remote`,
  etc.) are unrelated to firearm detection and are unaffected by this phase — they
  remain a separate, unaddressed limitation of the stock, non-fine-tuned model.
