# Phase 2O — Live System Audit (pre-Monday)

**Status: audit only. No code, threshold, geometry filter, or configuration changed.**
All findings below are traced from the actual code and, where noted, directly verified
against **real rows already in `database/dev.db` from this morning's live webcam test**
(2026-09-05, ~11:01–11:07 UTC) — not synthetic data.

## A. False object detections

### Path traced
`video-processing` (webcam/file/RTSP source) → `send_frame()` (HTTP POST, synchronous)
→ `/infer/frame` (`app/main.py`) → `pipeline.detect_frame()` → `YoloV8Adapter.detect()`
→ merged into one `detections` list → `window.add()` (`CameraWindow.entries`, pruned
every frame to `SEQUENCE_WINDOW_SECONDS`=6s) → `backend_client.send_detections()` (every
frame, always) + `evaluate_window()` (only every 6s) → backend `ingestDetections()` /
`ingestAction()` → Prisma `Detection`/`Action` rows + `broadcast()` → frontend
`useRealtime()` → `CameraHero`'s local `recentDetections` array.

### 1–3. Model, weights, threshold — confirmed directly from the loaded object, not docs
- **`YoloV8Adapter`** (`app/detection/yolov8_adapter.py`), the general-purpose detector —
  this, not the firearm adapter, produces every one of `person`, `toothbrush`, `tie`,
  `frisbee`, `cat`, `knife`, etc. All are stock **COCO** classes; `knife` is a genuine
  COCO class (dining-context training images per the model's own documentation).
- Weights: `models/yolov8n.pt`, COCO-pretrained, untouched (no fine-tuning) —
  `model.names` returns the full stock 80-class COCO list.
- Confidence threshold: **0.45** (`YOLO_CONFIDENCE_THRESHOLD`, `app/config.py`), a single
  global value applied uniformly to every class.

### 4. Are these real YOLO output, or created/transformed downstream?
**Real YOLO output — confirmed two ways:**
1. A controlled offline re-run of the exact production model (`models/yolov8n.pt`,
   conf 0.45) against 79 real webcam frames already on disk reproduced `cell phone`,
   `cat`, `tie`, `remote`, and `knife` independently, outside any live pipeline.
2. **Directly in this morning's live `Detection` rows** (`database/dev.db`,
   2026-09-05 11:01–11:07 UTC): `surfboard`, `scissors`, `remote`, `cell phone`,
   `toothbrush`, `tie`, `frisbee`, `banana` all appear, each as an isolated one-or-two
   frame blip, never sustained — e.g. `toothbrush` (0.79 confidence) appears at exactly
   one timestamp and never again; `surfboard` appears at two consecutive timestamps then
   vanishes. This is the signature of per-frame model noise, not a systematic bug
   downstream.

Two of these were visually verified against their source frames: a "cat" detection
(0.58) on a frame showing only a person's bare shoulder/hair against an overexposed
wall (no cat), and a "tie" detection (0.63) on a frame showing a person holding a real
knife (no tie) — both unambiguous model hallucinations on ordinary/blurry webcam
footage, no object of that class present.

**The knife detection itself, separately, was also verified genuine**: the source frame
for one of this morning's `knife` hits (0.77 confidence) shows an actual kitchen knife
held up to the camera. **Your observation that the system correctly detects a knife is
confirmed true** — this is real YOLO inference on a real object, same model and
mechanism as the false positives, just correctly triggered this time.

### 5–7. Stale display, rolling buffers, database replay
- **Backend/ai-service side: no staleness or replay issue.** `CameraWindow.prune()`
  evicts anything older than 6s every single frame — nothing lingers server-side.
- **Frontend: a real, confirmed staleness issue.** `live-monitoring/page.tsx` keeps only
  a local, in-memory array of the **last 8 raw `detection.created` WebSocket events**
  (`MAX_RECENT_DETECTIONS = 8`, `activityByCamera[...].detections`), with **no
  timestamp-based expiry at all** — an object only drops off once 8 *newer* detections
  arrive, however long that takes. `CameraHero.tsx` then tallies `objectCounts` by
  iterating this entire buffer, so a single stale hallucinated class from several
  frames ago is displayed with equal visual weight, at the same moment, as whatever is
  genuinely in view right now. **This is confirmed to be part of the problem** — even a
  rare one-frame hallucination stays visible far longer than the frame that produced it.
- **No database-replay issue.** The Live Monitoring page's detection panel is populated
  *only* from live WebSocket events, never from a REST fetch of historical `Detection`
  rows — confirmed by reading the full data flow; there is no other frontend page that
  renders raw `Detection[]` at all.

### 8–9. Class-specific filtering / per-class thresholds
**Neither exists.** `YoloV8Adapter.detect()` applies one threshold to every box from
every class, with no allow-list, block-list, or per-class override anywhere in
`ai-service` or `backend` (confirmed by grep across both — zero matches for any such
mechanism).

### 10. Would raising the global threshold affect knife detection?
**Yes, unavoidably, under the current architecture** — `knife` and `toothbrush` share
the exact same `self.confidence_threshold`. There is no way to raise it selectively
today. (A **display-side, non-model-touching alternative** is discussed under
Recommendations — this is why the threshold was not touched in this audit.)

### Classification of the false positives
**Both real model false positive AND frontend display issue — not a buffer/history
bug in the backend, and not a database-replay bug.** The model does genuinely
hallucinate occasional COCO classes on this project's webcam footage (confirmed, not
assumed); the frontend then has no mechanism to let a one-off hallucination age out of
view quickly, making the problem look worse and more persistent than it actually is
frame-to-frame.

## B. Knife threat score — 0.50 / MEDIUM

### The rule/formula actually responsible — traced and reproduced from a real incident
**There is no knife-specific rule anywhere in the codebase.** `knife` is never read by
`DemoHeuristicActionRecognizer` (it only ever inspects detections labeled `"person"`)
and never appears in `RuleBasedThreatEngine.BASE_SCORE_BY_ACTION` (only `weapon_detected`
— firearm-only — and the geometry-derived action vocabulary do). A knife detection
**cannot, structurally, produce a threat score by itself.**

**What actually happened, traced to a real row in `database/dev.db`
(`Alert.id = cmto9wqwp00lhwstfmq46f3ei`, 2026-09-05 11:02:10 UTC):**

```
type: close_contact   severity: MEDIUM   threatScore: 0.5
description: "4 people in close proximity to one another.
              Also detected: knife, scissors, surfboard."
```

Tracing backward:
- `RuleBasedThreatEngine`: base score for `close_contact` = **0.40**; proximity bonus
  (+0.10, since `min_proximity_ratio < 0.15`) = **0.50** exactly. `scoreToSeverity(0.50)`
  → **MEDIUM** (0.4–0.65 band). The arithmetic is correct and reproducible.
- `close_contact` requires `avg_persons >= 2` — but the actual `person` detections
  feeding this window (verified directly from `Detection.boundingBox`) were **three
  heavily overlapping boxes for what is, in every corroborating frame from this session,
  a single person testing the system alone**:
  `[68,93,385,479]`, `[41,141,545,480]`, `[71,67,613,479]` — near-identical region,
  same frame, same instant. This is a well-known YOLO/NMS artifact: a subject close to
  and filling most of the camera frame can survive non-max-suppression as multiple
  overlapping boxes. `DemoHeuristicActionRecognizer` has **no deduplication step** — it
  counts raw `person`-labeled boxes as if each were a distinct individual
  (`len([d for d in dets if d.object == "person"])`), so 3–4 overlapping boxes for one
  person register as "4 people," and their near-zero centroid distance registers as
  "close proximity."
- `TemplateCaptioner` separately, independently, appends **every** non-person object
  label seen anywhere in the same 6-second window to the description string — with no
  relationship to the score. The knife *was* genuinely in view (this session's testing
  clearly involved a real knife); `scissors` and `surfboard` were not (further
  hallucinations, same mechanism as Section A) — all three are listed with equal
  weight, none of them contributing anything to the 0.50 score.

**Direct answer to your question**: **0.50/MEDIUM is arithmetically consistent with the
existing (deterministic) formula, but the input that produced it — "4 people in close
proximity" — is corrupted by a genuine, previously-undocumented bug: duplicate/
overlapping detection boxes for a single person being counted as multiple people.** The
knife's presence in the description is coincidental captioning, not causal. **This is
not a knife-scoring bug — because no knife-scoring path exists — it is a person-counting
bug that happened to coincide with a knife being tested.**

Answering your specific sub-questions directly:
- Knife has an explicit weapon rule? **No.**
- Knife uses generic object-threat scoring? **No — no object other than `person`
  (indirectly, via geometry) and `firearm` (via the dedicated weapon path) influences
  the score at all.**
- Does detection confidence affect threat score? **No** — `ActionObservation.confidence`
  is computed and stored but never read by `RuleBasedThreatEngine.assess()`.
- Does persistence affect this score? **No** — persistence (K-of-window) applies only
  to the firearm path; the geometry/action window evaluates on its own 6-second cadence
  regardless.
- Does action/geometry affect the score? **Yes — this is the entire mechanism, and the
  bug is inside it** (see above).
- Is the score simply hardcoded/default? **No, it's computed — but from a corrupted
  input.**
- Is MEDIUM the intended severity for a genuine close-contact reading? **Plausibly yes,
  by original design** (two people briefly close together isn't necessarily violent) —
  but this specific instance's "close_contact" classification is itself invalid.

### Recommendation (not implemented — for your review)
**Do not add a blanket "knife → CRITICAL" rule** — per your own instruction, and because
the evidence doesn't support treating "a knife is visible" alone as a defensible
CRITICAL trigger (COCO's knife class is trained on dining-context images; the same
model that correctly found a real knife also mislabeled other frames "scissors" and
"tie" in the same session — knife-class confidence alone is not yet a reliable
weapon signal the way the dedicated firearm model at least attempts to be).

Two independent, smaller, more defensible changes, presented separately so you can
choose either, both, or neither:

1. **Fix the actual bug**: collapse heavily-overlapping same-class (`person`) boxes
   before counting people in `DemoHeuristicActionRecognizer` (e.g. an IoU-based merge,
   the same category of fix NMS itself already does one layer up). This fixes
   `close_contact`/`fighting_candidate`/`approaching` misfires generally — not
   knife-specific, but this is the actual root cause found here.
2. **If a knife-aware signal is wanted**, the smallest defensible version mirrors the
   firearm path's own already-established distinctions (your examples): treat a knife
   detected **in isolation** differently from a knife **co-located with a person in
   close proximity** (using the *corrected*, deduplicated proximity signal from #1) —
   e.g. a modest, non-CRITICAL bump only in the second case, analogous to how
   `close_contact`/`fighting_candidate` already scale with genuine proximity, not a new
   independent weapon-style path. This still requires deciding an actual number, which
   should be your call, not one I pick unilaterally.

## C. "DEMO" / mock / heuristic audit — exact, from the code

| Component | Implementation | Real-time? | Learned model? | Classification | Demo Monday? |
|---|---|---|---|---|---|
| Person/object detection | `YoloV8Adapter`, COCO-pretrained YOLOv8n | Yes | Yes (pretrained, not fine-tuned by this project) | **Real ML inference** | Yes — with the false-positive caveat in §A |
| Firearm detection | `YoloV8FirearmAdapter`, fine-tuned YOLOv8n, single class | Yes | Yes (fine-tuned) | **Real ML inference**, accuracy **unvalidated** (Phase 2L/2M: high false-positive rate, poor recall at distance) | Only with that caveat stated |
| Knife detection | Same `YoloV8Adapter` as row 1 — no separate model/adapter exists | Yes (detection) / **no scoring path exists** | Yes (detection only) | **Real ML inference for the label; zero downstream reasoning about it** | Yes for "detects a knife"; **no** for any threat-level claim tied to it |
| Action recognition | `DemoHeuristicActionRecognizer` — bounding-box proximity/speed rules | Yes (real geometry) | **No** | **Heuristic**, explicitly `mode="DEMO"` in code; confirmed bug: no box-deduplication (§B) | Yes, if labeled heuristic and the bug is disclosed |
| Violence recognition | `X3DViolenceAdapter` (frozen X3D-S + Phase 2C head), **disabled by default** (`X3D_ADAPTER=none`) | If enabled, yes | Yes (frozen backbone + small trained head) | **Real inference when enabled**; Phase 2I found **0/12 recall** on staged-aggressive test clips | **No** — leave disabled, do not present as working |
| Nonviolence recognition | Same X3D adapter (binary head) *or* the heuristic's `no_activity`/`standing` baseline | Same as above / yes | Same as above / no | Same caveat / **heuristic default-case reading** | No / yes (as a heuristic baseline only) |
| Caption generation | `TemplateCaptioner` — fixed sentence templates + object-count listing | Yes (real inputs) | **No** | **Deterministic template**, `mode="DEMO"`; confirmed to list hallucinated objects with no filtering (§A/§B) | Yes, if labeled template-based |
| Threat engine | `RuleBasedThreatEngine` — hand-set weights, fully transparent | Yes | **No** | **Deterministic rules**, `mode="DEMO"` (one real branch: `weapon_detected`); confirmed vulnerable to corrupted geometry input (§B) | Yes, if labeled rule-based, not "AI-scored" |
| Alert generation | `threatEngine.service.ts` — real code, deterministic threshold mapping | Yes | N/A (no model) | **Real software**, not mock — reliability limited by its inputs above | Yes |
| Incident creation | Same service, HIGH/CRITICAL only | Yes | N/A | **Real software** | Yes |
| Database persistence | Prisma/SQLite, real writes on every real event | Yes | N/A | **Real**, confirmed via live rows (§E) | Yes |
| WebSocket events | `broadcast()`, real push on every write | Yes | N/A | **Real** | Yes |
| Frontend live monitoring | Real WebSocket-driven info panel; video preview is an **honest placeholder** (explicitly, in its own code comments — not implemented, not faked) | Panel: yes. Video: no (by design, disclosed) | N/A | **Real data, no live video decode** — already honestly labeled in-app | Yes, panel only — do not imply live video exists |
| Camera/video ingestion | `video-processing` — webcam/file/RTSP sources, real HTTP forwarding | Yes | N/A | **Real**, but see §D for actual achieved throughput | Yes |
| Notifications | `LOG` provider only | Yes (logs to console) | N/A | **Development-only provider** — real email/SMS/push are unimplemented interfaces | Document as limitation, already is |

This table matches what `docs/ai-pipeline.md`, `docs/demo.md`, and `models/README.md`
already state — the existing documentation was **not found to overstate anything** in
this audit; the gap is between the documentation and what's rendered/said live during a
demo (e.g., nothing currently tells a viewer live that "close_contact" is a heuristic
reading of possibly-duplicated boxes).

## D. Real-time audit

- **Configured sample rate**: `SAMPLE_FPS=2` (`video-processing/src/config.py`) → a
  0.5s sleep between frames.
- **Actual achieved rate, measured from this morning's real `Detection.frameTimestamp`
  deltas**: **~2.4 seconds between frames (~0.4 fps)**, not 0.5s. Root cause, found in
  `video-processing/src/pipeline.py`: `run()` sleeps `interval` seconds *after* a
  synchronous, blocking `send_frame()` call — the sleep does not account for how long
  the HTTP round trip + ai-service inference (general YOLO **and** firearm YOLO,
  serially, on CPU) actually took. The configured 2fps is a floor on the *gap*, not a
  target for the *total* cycle time.
- **Analysis window**: `SEQUENCE_WINDOW_SECONDS=6` — the heuristic/threat-engine
  re-evaluates at most every 6s; a firearm sighting bypasses this and is assessed
  immediately per-frame (subject to persistence/cooldown).
- **Frontend receives current WebSocket events**: yes — `useRealtime()` is a live
  WebSocket subscription, not polling, for `detection.created`/`action.detected`/
  `alert.created`/`alert.updated`.
- **Old detections remaining visible after the object leaves**: **yes, confirmed** —
  see §A5–7. This is the one place genuine staleness exists in the system.
- **Database records used to populate the live view**: no (confirmed §A) — only for the
  one-time seed of the latest existing alert on page load, not for detections.

**Conclusion: the system is genuinely processing live frames end-to-end, not replaying
stored results** — the false-positive and staleness issues are real, but they are not
evidence of a fake/replayed pipeline. Throughput is materially slower than configured,
which is worth knowing but is not itself a correctness bug.

## E. Database audit

Schema (`database/schema.prisma`) — one item worth flagging up front: **there is no
separate `Caption` table.** A caption is stored as `Action.description` (nullable
string) — persisted, but as a field on Action, not its own entity.

| Model | Stores | Written by | Linked to camera? | Timestamps | Linked to alert/incident? | Frontend reads it? |
|---|---|---|---|---|---|---|
| `Camera` | name, location, streamUrl, status, isDemo | `camera.service.ts` | — (is the anchor) | createdAt/updatedAt | via relations | Yes (Cameras page, Live Monitoring) |
| `Detection` | objectLabel, confidence, boundingBox (JSON string), mode, frameTimestamp | `inference.service.ts: ingestDetections()`, on every `/api/inference/detections` POST | Yes | frameTimestamp + createdAt | No | Yes, live only (§A), never historically |
| `Action` | label, confidence, **description (caption)**, mode, windowStart/End, threatScoreHint | `inference.service.ts: ingestAction()`, on every `/api/inference/actions` POST | Yes | windowStart/End + createdAt | Yes (`Alert.actionId`, optional) | Yes, live (`action.detected`) |
| `Alert` | type, severity, confidence, description, status, mode, threatScore | `threatEngine.service.ts: evaluateAction()`, only when `scoreToSeverity()` is non-null | Yes | createdAt/updatedAt | Yes (`incidentId`, optional) | Yes (Alerts page, Live Monitoring hero) |
| `Incident` | title, eventType, severity, confidence, aiDescription, startTime/endTime, reviewStatus, isDemo | same service, only for HIGH/CRITICAL | No direct FK — via `Alert.incidentId` and `VideoSegment` | startTime/endTime + createdAt/updatedAt | Yes (is the parent) | Yes (Incidents page) |
| `Notification` | channel, status, recipient, error, sentAt | `notification` service, only for HIGH/CRITICAL alerts | via Alert | createdAt + sentAt | Yes (`alertId`) | Not directly surfaced in UI beyond alert detail |
| `SystemEvent` | type, message, severity | defined in schema; **not found to be written anywhere in the audited code** | Optional | createdAt | No | Not surfaced |
| `VideoSegment` | filePath, startTime/endTime, isDemo | defined in schema; **not found to be written anywhere in the audited code** | Yes | startTime/endTime + createdAt | via Incident | Not surfaced |
| `User` | email, passwordHash, name, role | seed script / auth registration path | N/A | createdAt/updatedAt | N/A | Auth only |

**`SystemEvent` and `VideoSegment` are defined in the schema but this audit found no
active write path for either** — they exist for future use (camera online/offline
events, recorded incident clips) but are not currently populated by anything in the
live pipeline. Confirmed by the current row counts below (both 0).

### Real verification — actual current row counts (`database/dev.db`, checked live)

| Table | Row count (now) |
|---|---|
| Camera | 1 |
| Detection | 1,124 |
| Action | 405 |
| Alert | 41 |
| Incident | 32 |
| Notification | 32 |
| SystemEvent | 0 |
| VideoSegment | 0 |
| User | 1 |

**This audit did not run a new controlled camera test itself — no physical camera is
attached to this environment.** Instead, this morning's *already-recorded* live test
session (2026-09-05 11:01–11:07 UTC, visible directly in the numbers above and quoted
throughout §A/§B) served as the real verification: it is genuinely present in the
database, with real timestamps, real bounding boxes, and one real Alert/Incident pair —
proof the write path works end-to-end for actual live traffic. If you want a fresh
before/after delta captured live, running `video-processing` normally against a camera
right now and re-querying these counts afterward will show the increase directly — I
can do this if you start a camera session, or I can drive one synthetic-but-real POST
through `/infer/frame` using a real image on request.

## F. Monday priority order

Your suspected P0 list is **confirmed correct by the evidence**, with one addition:

**P0 — must fix before Monday:**
1. **False object detections shown as current** — primarily a **frontend display fix**
   (expire/deduplicate the rolling detection buffer by time and by IoU-overlap), not a
   model change — protects the working knife detection exactly as you required.
2. **The duplicate-person-box → inflated count → false close_contact/MEDIUM path** —
   this is the actual, newly-confirmed root cause behind issue #2, not "knife scoring."
   Fixing person-box deduplication in `DemoHeuristicActionRecognizer` is smaller and
   more defensible than inventing a new knife rule.
3. **Live-vs-historical clarity** — same underlying fix as #1, plus not letting a
   caption casually imply causality it doesn't have (e.g., "Also detected: X, Y, Z"
   reads as diagnostic evidence for the score when it is not).
4. **Truthful DEMO understanding** — delivered as this audit; recommend sharing §C's
   table (or an equivalent) with whoever observes the Monday demo, so no one draws the
   same "knife caused MEDIUM" inference again live.

**P1 — important, can be simplified for Monday:**
- General robustness of the person-counting heuristic beyond this one incident.
- Whether/how to add any knife-proximity signal at all (§B recommendation #2) — a
  product decision, not purely technical, and explicitly not required to be solved by
  Monday.
- Firearm detector's documented scene-realistic recall gap (Phase 2L/2M) — already
  known and already honestly documented; no new action strictly required for Monday.

**P2 — document as limitation:**
- X3D violence/nonviolence classifier's validated near-zero recall (already disabled,
  already documented).
- `SystemEvent`/`VideoSegment` being unpopulated.
- Notification providers being LOG-only.
- Achieved ~0.4fps vs. configured 2fps throughput (§D) — not incorrect, just slower
  than the config file implies; worth a documentation note, not a Monday fix.

## G. Regression tests — run as part of this audit

| Suite | Result |
|---|---|
| ai-service (`pytest`) | **94/94 passed** |
| backend (`npm test`) | **21/21 passed** |
| frontend (`npm test`) | **34/34 passed** |

All 149 existing tests pass, unchanged — nothing in this audit modified any source
file; only read/traced code and queried the existing database.
