# ai-service

The pluggable AI inference pipeline: object detection → action recognition →
captioning → temporal threat assessment. See
[`../docs/ai-pipeline.md`](../docs/ai-pipeline.md) for exactly which stages are real
models vs. clearly-labeled demo adapters, and why.

## Setup

Use **Python 3.12**, not the newest CPython installed — PyTorch/Ultralytics wheel
availability lags behind new Python releases. On this project's dev machine that meant
`py -3.12` specifically (there was also a 3.14 install that does NOT work here).

```bash
cd ai-service
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

The first real inference request downloads YOLOv8n's pretrained weights (~6MB) into
`../models/yolov8n.pt` automatically via `ultralytics`.

## Running

```bash
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Check `GET /health` — it reports which adapter is active for each stage.

## Endpoints

- `GET /health` — adapter status.
- `POST /infer/frame` — `{ camera_id, frame_timestamp, image_base64 }` → runs object
  detection on one frame, buffers it into that camera's rolling window, forwards
  detections to the backend, and — if the window's evaluation interval has elapsed —
  also runs action recognition + captioning + threat assessment and forwards that too.
- `POST /infer/sequence?camera_id=...` — manually triggers the action/caption/threat
  evaluation over whatever is currently buffered for that camera, without waiting for
  the time-based trigger. Useful for tests/demos.
- `POST /demo/simulate-scenario?camera_id=...` — plays a scripted DEMO escalation
  timeline (standing → approaching → aggressive movement → physical contact → potential
  fight) against a real camera ID, so the full alert/incident pipeline can be
  demonstrated without real footage or trained models. See
  [`../docs/demo.md`](../docs/demo.md).

## Testing

```bash
venv\Scripts\pytest -v
```

Tests run with `DETECTION_ADAPTER=mock` (see `tests/conftest.py`) so they don't need to
load the real YOLO model — fast and deterministic. The real YOLOv8 adapter is verified
manually (see the root README) since downloading/loading a real model in every test run
would be slow and network-dependent.

## Adapter configuration

Set via `.env` — see `.env.example` for every variable and
[`../docs/ai-pipeline.md`](../docs/ai-pipeline.md) for what each adapter actually is.
