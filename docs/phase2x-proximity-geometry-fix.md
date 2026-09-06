# Phase 2X — Proximity Geometry Normalized Against the Real Frame

**Status: implemented, tested (8 new tests, 228/228 total passing).** Fixes the geometry
input only — no threshold, base score, bonus, or severity mapping was changed. A real,
measured trade-off was found and is reported honestly, not hidden: see "Remaining
issues" below.

## Root cause

`_frame_diagonal_estimate()` in `demo_heuristic.py` computed a "frame diagonal" from
the spread of the detected person boxes themselves (`max(xs)-min(xs)`, `max(ys)-min(ys)`,
×3), not from the real camera frame. When two people both span most of the frame's
height (normal webcam framing), this inflates the estimate and can make a real,
moderate horizontal separation compute as "close."

## Change made

- `app/main.py`: passes the real decoded frame's `width`/`height` (from `image.shape`)
  into `window.add()`.
- `app/common/frame_buffer.py`: `CameraWindow` gained `last_frame_width`/
  `last_frame_height` (updated by an optional `add()` parameter; `None` until first
  supplied — every existing caller that never supplies them is unaffected).
- `app/services/pipeline.py`: `evaluate_window()` passes `window.last_frame_width`/
  `last_frame_height` into `get_action_adapter().recognize(...)`.
- `app/action_recognition/base.py`: the `ActionRecognitionAdapter.recognize()` ABC
  gained optional `frame_width`/`frame_height` parameters (additive, mirrors how
  `clip_frames` was added in Phase 2H) — X3D/S3D adapters are never called with these
  and needed no changes.
- `app/action_recognition/demo_heuristic.py`: `recognize()` and `_proximity_and_speed()`
  accept the new optional params; when both are provided, the proximity ratio is
  computed against `math.hypot(frame_width, frame_height)` (real geometry) instead of
  `_frame_diagonal_estimate()`. **When not provided (every pre-Phase-2X caller/test),
  behavior is byte-identical to before** — `_frame_diagonal_estimate()` itself is
  unmodified and remains the fallback.

**Not touched**: `CLOSE_PROXIMITY_RATIO`, `PROXIMITY_BONUS`, `BASE_SCORE_BY_ACTION`,
`FAST_MOVEMENT_PX_PER_SEC`, the escalation bonus, knife persistence settings, severity
mapping, Phase 2T, BLIP, firearm (remains removed), general object detection.

## Before vs after (real data)

| Case | Old diagonal | Old ratio | New (real 640×480) diagonal | New ratio | Old label | New label |
|---|---|---|---|---|---|---|
| Real "opposite sides of frame" pair (Phase 2W audit) | 2383.5 (box-derived) | 0.112 (close) | 800.0 | 0.334 (not close) | `close_contact` | not `close_contact` |
| Real adjacent pair, moment before the real CRITICAL escalation | ~2391 | 0.117 (close) | 800.0 | 0.36 (not close) | `close_contact` | `standing` |

## Threat regression results (real replay, real adapter classes)

- Calm one person: `standing`, 0.05 — unaffected.
- Two people genuinely close (constructed, containment 0.52 — distinct people, not a
  duplicate box; centroids 110px apart): still `close_contact`, ratio 0.14 — the
  architecture still reaches close_contact for real close contact.
- Real separated pair: no longer `close_contact` — the fix works as intended.
- Walking: unaffected.
- Approaching: still reachable (doesn't depend on proximity).
- **Real knife/close-contact → CRITICAL sequence, replayed with the real adapter
  classes and the real historical detection boxes: every window now reads `standing`
  (0.05) instead of the historical `close_contact(0.5) → fighting_candidate(1.0/0.85)`
  progression.** The real adjacent-pair geometry in this specific incident, measured
  against the true 800px diagonal, does not fall under the unchanged
  `CLOSE_PROXIMITY_RATIO=0.15`.

## Remaining issues (found during this phase, not fixed — out of scope by explicit instruction)

**`CLOSE_PROXIMITY_RATIO=0.15` was implicitly calibrated against the old, inflated,
box-derived diagonal — not real frame geometry.** Correcting the geometry without
recalibrating this threshold means the proximity-driven path to `close_contact`/
`fighting_candidate` becomes reachable only for much tighter physical proximity than
before (roughly 120px of true separation on a 640×480 frame) — genuinely close contact
still reaches it (see test above), but this project's one real recorded knife/CRITICAL
demonstration no longer does, because the two people in that real incident were not
that tightly overlapping. This is a direct, measured consequence of fixing the
geometry input alone, reported as required rather than compensated for by touching the
threshold this phase explicitly forbade changing.
