# AI Pipeline

## Pipeline stages

```
Video → Frame extraction → Object detection → Action recognition →
  Video/scene captioning → Temporal analysis → Threat assessment → Alert generation
```

Each stage is an abstract interface in `ai-service/app/<stage>/base.py`, with one or more
concrete adapters registered in `ai-service/app/config.py`. `backend` and `frontend`
never see adapter internals — only the structured JSON contract below.

## Honesty policy (read this before trusting any result field)

Every inference result carries a `mode` field: `"real"` or `"demo"`. The frontend renders
a visible **DEMO** badge on anything with `mode: "demo"`. Nothing simulated is ever shown
as if it were a real detection.

## Stage 1 — Object Detection

- **Adapter:** `YoloV8Adapter` (Ultralytics YOLOv8n, COCO-pretrained) — **real model**,
  CPU-capable, runs today. Verified working end-to-end in this project (see the root
  README's verification notes).
- **Supported classes:** all 80 stock COCO classes, including `person`, `car`, `truck`,
  `bus`, `motorcycle`, `bicycle`, and — notably — `knife` (a dining/kitchen-context COCO
  class). The full list is in `ai-service/app/detection/yolov8_adapter.py`
  (`COCO_CLASSES`). Person/vehicle detection is the reliable, intended use here.
- **Weapon/firearm detection — REMOVED (Phase 2V):** COCO has **no firearm/gun class at
  all**; its `knife` class remains this project's only weapon-adjacent general-detector
  signal (see Stage 4's knife-evidence floor below). A separate, purpose-built firearm
  detector (`YoloV8FirearmAdapter`, single-class `"Gun"`) was built, evaluated, and
  progressively hardened across Phases 2J, 2K, 2L, 2M, and 2U — and ultimately
  **removed entirely** in Phase 2V, because the accumulated evaluation evidence (Phases
  2K/2L: ~1-in-4 false-positive rate on ordinary footage; Phase 2T's live audit: real
  knife frames classified `"Gun"` at 0.74–0.76 confidence; Phase 2U's own mitigation
  still left 45% of known false positives trusted) did not establish reliable
  firearm-vs-non-firearm discrimination. This is **not** a claim that firearm detection
  is impossible in general, nor that knives and firearms have been reliably
  distinguished — see `docs/phase2v-firearm-removal.md` for the full before/after
  evidence and reasoning. The model file, its adapter code, and every
  firearm-persistence/scoring code path have been deleted from the active runtime; the
  weights file itself is retained on disk only for historical evaluation-script
  reproducibility (`models/README.md`).
- **Output contract:**
  ```json
  { "object": "person", "confidence": 0.94, "bounding_box": [x1, y1, x2, y2], "mode": "real" }
  ```

### Diagnostic frame capture (Phase 2J, disabled by default)

Live-webcam testing surfaced frequent false positives from the general detector on
ordinary footage (a person alone in a room) — `cat`/`dog`/`toothbrush` among them.
Before any threshold or model change, `app/common/diagnostic_capture.py` provides a way
to actually *see* what triggered a false positive, rather than tuning blind.

- **What it does**: for any detection whose class is in `DIAGNOSTIC_CAPTURE_CLASSES`
  (default: `knife` only, since Phase 2V — knife is now the most sensitive class in the
  active detection scope), saves the exact source frame (JPEG) plus a metadata sidecar
  (`timestamp`, `camera_id`, `class`, `confidence`, `bounding_box`, `adapter`, `mode`)
  to local disk under `DIAGNOSTIC_CAPTURE_DIR` (default:
  `ai-service/diagnostics/frames/<class>/`, git-ignored).
- **What it deliberately does not do**: change any detection result, touch the backend
  database or any API response, affect alert/threat behavior, or run on every frame —
  it's a pure side effect hung off detections that already happened, wired via
  `BackgroundTasks` in `app/main.py` so it can never add latency to the response path,
  and every write is wrapped so a failure here can never affect live inference.
- **Disabled by default** (`DIAGNOSTIC_CAPTURE_ENABLED=false`) — this saves real camera
  frames, potentially of a real person, so it must be explicitly opted into.
- **Bounded disk usage**: each configured class gets its own subfolder with its own
  cap (`DIAGNOSTIC_CAPTURE_MAX_FRAMES`, default 200), oldest evicted first — a burst of
  one class can never crowd out or evict evidence of another.

## Stage 2 — Action Recognition

- **Interface:** `ActionRecognitionAdapter.recognize(window)` consumes a rolling
  sequence of `(timestamp, detections)` — not a single frame — buffered per-camera by
  `ai-service/app/common/frame_buffer.py` over `SEQUENCE_WINDOW_SECONDS`.
- **Current adapter:** `DemoHeuristicActionRecognizer` — computes **real geometry** from
  whatever the detection stage produced (person bounding-box centroid proximity and
  movement speed across the window) and maps it to a small action vocabulary
  (`standing`, `walking`, `running`, `approaching`, `close_contact`,
  `fighting_candidate`, `no_activity`) via a hand-written, documented rule set (see
  `ai-service/app/action_recognition/demo_heuristic.py`). The inputs can be real (when
  running on real YOLOv8 detections); the *labeling rule* is a heuristic, not a trained
  classifier — hence `mode: "DEMO"` end to end.
- **Plug-in point:** `ActionRecognitionAdapter` (ABC) — a real implementation (e.g. a
  PyTorchVideo MViT/SlowFast checkpoint) can be dropped in without touching callers.

### Stage 2 refinement — X3D-S (optional, disabled by default)

- **What it is**: `X3DViolenceAdapter` (`app/action_recognition/x3d_violence_adapter.py`)
  — a real, frozen X3D-S backbone (Kinetics-400 pretrained, untouched) with a small
  logistic-regression classifier head trained in Phase 2C on top of its pooled
  features. Enabled via `X3D_ADAPTER=x3d_violence` (default: `none` — disabled,
  behavior identical to not having this section at all).
- **How it's wired in, and why**: it is *not* a replacement for the geometry heuristic
  above and it is *not* selected via `ACTION_ADAPTER` — it's an orthogonal, optional
  refinement layer. `pipeline.py`'s `evaluate_window()` calls it, via
  `maybe_refine_with_x3d()`, **only** when the heuristic's own reading for that window
  is already `close_contact` or `fighting_candidate`, and only if a per-camera cooldown
  (`X3D_EVAL_COOLDOWN_SECONDS`, default 15s) has elapsed and enough raw frames are
  buffered (`ai-service/app/common/clip_buffer.py`, separate from the detection-only
  window buffer). If it corroborates (predicts Violence at or above
  `X3D_CONFIDENCE_THRESHOLD`), it upgrades that window's `mode` from `DEMO` to `REAL`
  and its `confidence` to its own — **the label is never changed**, and a disagreement,
  a load failure, or an inference exception all leave the heuristic's original result
  completely untouched. It can only raise the honesty/confidence of an alert the
  heuristic already decided to raise; it can never invent one or suppress one.
- **What `mode="REAL"` means here, precisely — read this before trusting it**:
  it means genuine model inference actually ran and produced this result. **It does
  not mean violence was confirmed to have occurred, and it does not mean this
  classifier is independently validated as reliable.** The real evidence: training
  validation accuracy (99.6%/100% recall) is explicitly flagged in
  [`phase2c-training.md`](./phase2c-training.md) as inflated by a still-imperfectly-
  filtered data stratum, not to be trusted at face value. Real-camera evidence
  ([`phase2e-webcam-eval.md`](./phase2e-webcam-eval.md),
  [`phase2f-staged-positive-test.md`](./phase2f-staged-positive-test.md),
  [`phase2g-controlled-retest.md`](./phase2g-controlled-retest.md)) is more meaningful
  but still limited: correctly read real calm footage as NonViolence every time, and
  showed real motion-correlated behavior on staged clips including one confirmed
  threshold crossing — but that's n=3 confirmed-elevated-motion data points total, a
  non-monotonic relationship between raw motion and score, and no test yet against a
  genuine multi-person physical altercation on this camera.
- **CPU cost**: ~200–400ms per invocation on this project's dev CPU (i5-8250U, see
  [`x3d-benchmark.md`](./x3d-benchmark.md)) — gated and cooled-down specifically so this
  is rare, not per-frame. Runs via `asyncio.to_thread()` from `main.py` so it can never
  stall the 2 fps `/infer/frame` loop.
- **Failure behavior**: adapter construction and every inference call are wrapped in
  try/except (`pipeline.get_x3d_adapter()` / `maybe_refine_with_x3d()`) — any failure
  (dependency missing, checkpoint missing, bad clip) logs once and falls back to the
  heuristic's result for that window, never crashes `ai-service`.

## Stage 3 — Video Captioning

- **Interface:** `CaptioningAdapter.caption(detections, action)` returns a
  natural-language description.
- **Current adapter:** `TemplateCaptioner` — composes a sentence from detected object
  counts and the recognized action label (e.g. *"Two people approaching one another."*).
  Labeled `mode: "DEMO"` because it is templated, not a vision-language model.
- **Plug-in point:** `CaptioningAdapter` (ABC) — a real implementation (e.g. BLIP-2 or a
  video-LLaVA-style model) can replace it.

## Stage 4 — Temporal Analysis / Threat Assessment

- **This is the project's core research contribution.** `ThreatAssessmentAdapter.assess()`
  looks at the recognized action + its geometric metrics, plus the previous window's
  score (to detect a rising/sustained trend) — never a single frame — and returns a
  0.0–1.0 score with a rationale string.
- **Current implementation:** `RuleBasedThreatEngine`
  (`ai-service/app/threat/rule_based.py`) — fully transparent, hand-set weights: a base
  score per action label, +0.10 for close physical proximity, +0.05 for fast movement,
  and up to +0.15 for a rising/sustained trend across windows. Every point in the final
  score is traceable in the returned rationale string (e.g. *"base risk for
  'fighting_candidate' = 0.70 + close physical proximity (+0.10) + sustained/rising
  activity across recent windows (+0.15) = 0.95. Potential escalation to physical
  violence."*). This score is then handed to the **backend's** Threat Engine
  (`backend/src/services/threatEngine.service.ts` +
  `backend/src/config/threatConfig.ts`), which owns the score→severity thresholds and
  Alert/Incident creation — see `docs/architecture.md`.
- **Framing:** results are surfaced as **"Potential Threat / Escalation Prediction"** with
  a numeric score and a human-readable rationale — never as a claim of certainty about
  future events.
- **Plug-in point:** `ThreatAssessmentAdapter` (ABC) — a trained temporal sequence model
  can later replace the rule-based engine using the same interface.

## What requires custom training / data (not available today)

| Capability | What's needed |
|---|---|
| Reliable firearm detection | A pretrained single-class detector (`YoloV8FirearmAdapter`) was integrated, evaluated across Phases 2K/2L/2M/2U, and ultimately **removed in Phase 2V** — see `docs/phase2v-firearm-removal.md`. It never had a held-out validation set matching *this project's* actual camera conditions, and real testing found it firing on real knife frames at 0.74–0.76 confidence. Re-adding firearm detection would need genuine confirmed-positive evaluation data in this project's own deployment conditions (none exists today) before it could be trusted, plus fine-tuning if firearm/knife confusion needs to be addressed directly. |
| Real action recognition (fighting/pushing/striking) | A labeled video-action dataset (e.g. a violence-detection or activity-recognition corpus), a GPU for training a temporal model, and an evaluation protocol. |
| Real video captioning | Either an API-based hosted VLM, or a locally-run open-weight video-captioning model + GPU for acceptable latency. |
| Trained temporal threat model | Historical labeled incident sequences (which don't exist without real deployment data) to move beyond the rule-based engine. |

## Endpoints (ai-service)

- `GET /health` — which adapter is active for each stage.
- `POST /infer/frame` — `{camera_id, frame_timestamp, image_base64}`. Runs Stage 1 on
  the frame, buffers it into that camera's window, forwards detections to the backend,
  and — once the window's evaluation interval has elapsed — also runs Stages 2-4 and
  forwards that result too. This is the endpoint `video-processing` calls per sampled
  frame; see `docs/architecture.md`.
- `POST /infer/sequence?camera_id=...` — manually triggers Stages 2-4 over whatever is
  currently buffered, without waiting for the time-based trigger (used by tests/demos).
- `POST /demo/simulate-scenario?camera_id=...` — plays a scripted DEMO escalation
  timeline (standing → approaching → aggressive movement → physical contact → potential
  fight) directly against the backend for a given camera, bypassing frame analysis
  entirely. Verified end-to-end in this project: it correctly produces LOW → MEDIUM →
  HIGH → CRITICAL alerts and a backend-created Incident once severity crosses HIGH. See
  `docs/demo.md` and `ai-service/app/services/demo_scenario.py`.

## Verified in this project

Unlike a spec that only describes intended behavior, the pieces above have been run:
real YOLOv8n loading and inferring on a frame (see `ai-service/README.md`), the full
video-processing → ai-service → backend chain forwarding a real (zero-detection, on
synthetic blank footage) result end-to-end, and the demo scenario producing the exact
LOW→MEDIUM→HIGH→CRITICAL escalation with a backend-created Alert + Incident.
