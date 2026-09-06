# Demo Mode

## Why Demo Mode exists

Real CCTV/RTSP hardware and fully-trained surveillance-specific models are not available
during development of this project. Demo Mode lets the whole system — dashboard, alerts,
incidents, analytics, WebSocket updates — be exercised end-to-end using:

- pre-recorded sample video files (in place of live RTSP), and/or
- the local webcam, and/or
- available real models (YOLOv8 object detection) running for real on that footage, with
  the not-yet-available stages (action recognition, captioning, weapon detection, and by
  extension threat scoring built on top of them) filled by clearly labeled mock adapters.

## The rule

**Every simulated or demo-sourced event is labeled `DEMO` everywhere it appears** —
dashboard cards, alert list, incident detail, exported reports. Demo incidents are never
presented as, or mixed silently with, real security events. Internally this is the same
`mode: "real" | "demo"` field described in [`ai-pipeline.md`](./ai-pipeline.md), plus a
`Camera.status` of `DEMO`-sourced vs a live/RTSP source.

## What "Demo Mode" toggles

1. `video-processing` reads from a bundled/uploaded demo video file instead of an RTSP
   URL.
2. `ai-service` continues to run its real adapters where available (object detection) and
   its mock adapters where a real model isn't wired in yet (action recognition,
   captioning, weapon detection) — both cases are tagged with `mode` per the contract in
   ai-pipeline.md, so the dashboard's DEMO badge is always accurate, not hardcoded to "on
   for the whole system".
3. Seeded/sample cameras, alerts, and incidents used for first-run dashboard population
   are tagged `isDemo: true` in the database and visually badged in the UI.

## Running it

**Option A — scripted scenario (no video needed at all).** With `backend` and
`ai-service` running, POST to ai-service:

```bash
curl -X POST "http://localhost:8000/demo/simulate-scenario?camera_id=<a real camera id>"
```

This plays out, over ~16 seconds, the exact escalation example from
`docs/ai-pipeline.md` Stage 4 (standing → approaching → aggressive movement → physical
contact → potential fight), posting each step to the backend as `mode: "DEMO"`. **Verified
in this project**: it correctly produces a LOW alert, then MEDIUM, then HIGH (which also
creates an Incident), then CRITICAL — visible immediately on the Alerts/Incidents pages
via the live WebSocket feed, with the DEMO badge on every one.

**Option B — real inference on an uploaded/demo video file**, using the real YOLOv8
detector against actual footage (see `video-processing/README.md`):

```bash
cd video-processing
venv\Scripts\python -m src.run_camera --camera-id <id> --source file --path C:\path\to\demo.mp4
```

Detections are real (`mode: "REAL"`); the action/caption/threat layers built on top of
them are still `mode: "DEMO"` (heuristic, not trained models) — see
`docs/ai-pipeline.md`.

**Option C — webcam**, same command with `--source webcam --device 0`. This is genuinely
live video, but it's still not a CCTV/RTSP feed — the camera's `isDemo` flag in the
backend should reflect what it actually is in each case.
