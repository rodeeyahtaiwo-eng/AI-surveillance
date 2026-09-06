# video-processing

Reads a camera source — webcam, an uploaded/demo video file, or a real RTSP stream —
samples frames at a configurable rate, and forwards each sampled frame to `ai-service`
for inference. Deliberately lightweight (no torch/ultralytics): this could run on a
low-power ingestion box separate from whatever runs the AI models. See
[`../docs/architecture.md`](../docs/architecture.md).

## Setup

```bash
cd video-processing
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

## Running

The `--camera-id` must match a camera already registered in the backend (add it first
via the Cameras page or `POST /api/cameras`). This script only ingests video for a
camera that already exists — it does not create one.

**Webcam** (real, live — but still not a CCTV/RTSP feed):
```bash
venv\Scripts\python -m src.run_camera --camera-id <id> --source webcam --device 0
```

**Uploaded/demo video file** (loops automatically; tag the camera `isDemo: true` in the
backend — see [`../docs/demo.md`](../docs/demo.md)):
```bash
venv\Scripts\python -m src.run_camera --camera-id <id> --source file --path C:\path\to\demo.mp4
```

**Real RTSP camera** (untested against physical hardware in this project — see the root
README's Limitations section):
```bash
venv\Scripts\python -m src.run_camera --camera-id <id> --source rtsp --url rtsp://user:pass@host:554/stream
```

Add `--max-frames N` to stop after N frames (useful for a quick smoke test).

## What it does NOT do

- It does not send raw frames through the backend's normal REST API — only to
  `ai-service`, and only at `SAMPLE_FPS` (not every frame). See
  [`../docs/architecture.md`](../docs/architecture.md) "Real-time processing".
- It does not run any AI inference itself — that's `ai-service`'s job. This service only
  captures and samples frames.
- It does not orchestrate multiple cameras automatically. For this build, run one
  process per camera you want to ingest (`run_camera.py` per camera ID). Auto-spawning a
  process per camera from the Cameras table is a natural next step, not implemented here.

## Testing

```bash
venv\Scripts\pytest -v
```
