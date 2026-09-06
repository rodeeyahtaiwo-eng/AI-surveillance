# Phase 2D — Webcam Recording Diagnosis, Fix, and Clip Inspection

**Status: diagnosis + data collection only.** No retraining happened in this phase, per
the phase instructions — see [`phase2c-training.md`](./phase2c-training.md) for the
classifier that still awaits fresh accuracy numbers once these clips are used. Nothing
under `app/`, threat scoring, captioning, next-event prediction, or the frontend was
touched.

## Diagnosis: it was never the lens or the room

Phase 2C's recording script opened the camera with `cv2.VideoCapture(device)` — no
explicit backend — which OpenCV resolved to **MSMF**, and got frames averaging
~13-14/255 brightness across every attempt, which was reported (correctly, at the time)
as consistent with a covered lens or a dark room.

A dedicated diagnostic (`scripts/diagnose_webcam.py`) tested three backends explicitly
and captured 30 frames from each, tracking the brightness trend and saving a preview
frame per backend:

| Backend | Frame 1 brightness | Frame 30 brightness | Verdict |
|---|---|---|---|
| `CAP_ANY` (default → resolved to MSMF) | 20.2 | 13.8 | Never recovers within 30 frames |
| `CAP_DSHOW` | **207.8** | 196.5 | Correct exposure from the first frame |
| `CAP_MSMF` (explicit) | 13.4 | 187.8 | Recovers, but takes most of a 2-second window |

**Root cause: auto-exposure convergence, not hardware.** The camera (`HP HD Camera`,
confirmed present and `Status: OK` via `Get-PnpDevice`) and Windows camera privacy
settings (confirmed `Allow` at both machine and user level via the registry) were never
the problem. `CAP_DSHOW` reaches full exposure essentially immediately; the default
backend either converges too slowly for a short clip or doesn't converge at all within
the window Phase 2C used. The `CAP_DSHOW` preview frame was visually inspected and
confirmed to be a clear, correctly-exposed, real image — not visual noise that happened
to average bright.

## Fix

`scripts/record_webcam_clips.py` now:
1. Opens the camera with `cv2.CAP_DSHOW` explicitly (proven immediate in diagnostics),
   instead of the unspecified default backend.
2. Reads and discards a 1.5s warm-up period **before** recording starts, as
   defense-in-depth against any future driver/backend variance — so a slow-converging
   backend can no longer silently produce unusable output the way it did in Phase 2C.
3. Still measures and reports per-clip brightness rather than assuming the fix worked —
   the `MIN_USABLE_BRIGHTNESS` gate from Phase 2C is unchanged, it's just no longer
   tripping.

## Recorded clips

8 clips recorded, `datasets/webcam_normal/webcam_normal_000.mp4` through `_007.mp4`
(git-ignored, per `ai-service/datasets/` in `.gitignore` — not committed, consistent
with how RLVS itself is handled). All 8 fully decode-clean.

| Property | Value |
|---|---|
| Count | 8 |
| Resolution | 640×480 (all 8) |
| Frame rate | 15.0 fps (all 8) |
| Duration | 4.0s each (60/60 frames decoded, all 8) |
| File size | 197–245 KB each |
| Brightness (avg) | 132.9–137.2 / 255 — consistent, well above the 25.0 usability floor |
| Frame-to-frame brightness std (within a clip) | 0.18–0.49 — very stable, no flicker |
| Decode failures | 0 |

## Qualitative observations (technical/compositional only — see note below)

- **Fixed camera, not handheld** — this is a genuine, direct match for the
  fixed-camera-surveillance framing the whole project is built around, and something
  RLVS's NonViolence class (dominated by produced/broadcast content) could never
  provide regardless of filtering.
- **Consistent indoor lighting**, no visible flicker or exposure hunting during
  recording (confirmed by the low per-clip brightness std above).
- **Single subject, relatively low motion within each 4s clip** (implied by the very
  low frame-to-frame brightness variance, and consistent with a short seated recording
  session) — worth flagging honestly as a **coverage limitation**: this batch leans
  toward "present but still," not a range of ordinary activity (walking into/out of
  frame, moving around the room, etc.). It's a legitimate example of calm/non-violent
  presence, but a narrow one. If more webcam clips are recorded later, varying the
  activity (not just the person) during capture would add more value than recording
  more near-identical still clips.
- **Note on this section**: recordings are of a real person in a real room. This
  document intentionally describes only technical/compositional properties (framing,
  motion, lighting) needed to judge training suitability — not appearance or identity —
  and the clip files themselves are git-ignored and stay local, the same handling
  already established for RLVS.

## What this changes vs. Phase 2C

Phase 2C's classifier was trained and evaluated **without** any usable webcam clips —
the `datasets/webcam_normal/` folder was empty of usable content at that time, and the
skepticism applied to the 99.6%/100% recall result in `phase2c-training.md` still
stands untouched by this phase. These 8 clips are now available as real,
deployment-domain NonViolence examples, but **have not yet been added to the feature
cache, split, or classifier** — per the instruction for this phase, no retraining or new
accuracy numbers are reported here. That remains a deliberate next step, not done yet.

## Regression check

`pytest` re-run after these changes: unaffected (this phase touched only
`scripts/record_webcam_clips.py` and added `scripts/diagnose_webcam.py`, neither
imported by the test suite or by anything under `app/`).
