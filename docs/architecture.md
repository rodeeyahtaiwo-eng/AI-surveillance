# Architecture

## Overview

The AI Surveillance & Early Threat Detection System is split into four independently
runnable services plus a shared database, so that the web application never has a hard
dependency on any specific AI model:

```
┌─────────────┐      HTTPS/WS       ┌─────────────┐      SQL       ┌──────────────┐
│  frontend   │ ◄─────────────────► │   backend   │ ◄─────────────► │  PostgreSQL  │
│  (Next.js)  │                     │  (Express)  │                  │  / SQLite    │
└─────────────┘                     └──────┬──────┘                 └──────────────┘
                                            │ HTTP (webhook: results in)
                                            │ HTTP (config out)
                                     ┌──────▼──────┐
                                     │ ai-service  │
                                     │  (FastAPI)  │
                                     └──────┬──────┘
                                            │ HTTP (frames in)
                                     ┌──────▼───────────┐
                                     │ video-processing  │
                                     │ (OpenCV/FFmpeg)   │
                                     └──────┬────────────┘
                                            │ reads
                                  RTSP / webcam / demo file
```

## Why four services instead of one monolith

- **frontend** never talks to AI models directly — it only ever talks to `backend`.
  This means the AI stack can be swapped, upgraded, moved to a GPU box, or replaced by a
  totally different vendor model without touching a single dashboard component.
- **backend** owns the database, auth, business rules (alert thresholds, roles) and the
  real-time event fan-out (WebSocket). It treats `ai-service` as a pluggable, replaceable
  microservice reachable over HTTP.
- **ai-service** owns model inference only. Every pipeline stage (detection, action
  recognition, captioning, threat scoring) is defined as an abstract interface with a
  concrete adapter behind it, so a real trained model can be dropped in later by writing
  one new adapter class — no changes to the API contract, the backend, or the frontend.
- **video-processing** owns frame acquisition (RTSP / webcam / uploaded demo video) and
  sampling. It is deliberately kept out of the request/response path of the REST API —
  raw video/frames are never sent through the normal CRUD API. It pushes sampled frames
  to `ai-service`, and forwards results to `backend`.

## Request / event flow

**Configuration (synchronous, REST):**
`frontend → backend → PostgreSQL/SQLite` for cameras, users, alert thresholds, settings.

**Inference pipeline (near real-time) — implemented and verified live in this project:**
1. `video-processing` reads a camera source (RTSP URL, webcam index, or a demo video
   file) and samples frames at `SAMPLE_FPS` (default 2/sec — deliberately not every raw
   frame).
2. Each sampled frame is POSTed to `ai-service`'s `POST /infer/frame`.
3. `ai-service` runs Stage 1 (Object Detection) on that frame immediately, and buffers
   the result into a per-camera rolling window. Once the window's evaluation interval
   (`SEQUENCE_WINDOW_SECONDS`) has elapsed, it also runs Stages 2-4 (Action Recognition →
   Captioning → Threat Assessment) over the buffered window.
4. `ai-service` itself — not `video-processing` — POSTs the structured result to
   `backend`'s ingestion endpoints (`POST /api/inference/detections`,
   `POST /api/inference/actions`), authenticated with a shared `INGEST_API_KEY` rather
   than a user JWT. (A scripted demo timeline can also call these endpoints directly via
   `ai-service`'s `POST /demo/simulate-scenario`, bypassing frame analysis entirely — see
   `docs/demo.md`.)
5. `backend` persists `Detection` / `Action` rows, broadcasts them, and — for actions —
   runs the **Threat Engine** (`src/services/threatEngine.service.ts`): maps the raw
   threat score to a severity (`src/config/threatConfig.ts`) and, if it clears the LOW
   threshold, creates an `Alert`; HIGH/CRITICAL also creates an `Incident` and dispatches
   a notification.
6. `backend` broadcasts each event (`detection.created`, `alert.created`, etc.) over
   WebSocket to every connected dashboard client. The dashboard updates live, with no
   polling and no full-page refresh.

## Folder structure

```
AIsurveillance/
├── frontend/           Next.js (App Router) + TypeScript + Tailwind — the admin dashboard
├── backend/             Express + TypeScript API, Prisma ORM, WebSocket server, auth
├── ai-service/          Python FastAPI — pluggable AI inference pipeline
├── video-processing/    Python — camera/video ingestion + frame sampling
├── database/            Prisma schema (single source of truth for the data model)
├── models/               Where downloaded/trained model weights live (git-ignored)
├── docker/               docker-compose + Dockerfiles for all services
├── docs/                 This documentation set
└── tests/                Cross-service / end-to-end tests
```

## Replaceability contract

Every AI capability is defined as a TypeScript-like interface (in Python, an `ABC`) in
`ai-service/app/<stage>/base.py`. Swapping a model means:

1. Implement a new adapter class satisfying that interface.
2. Register it in `ai-service/app/config.py` (or via `.env`, e.g. `DETECTION_ADAPTER=yolov8`).
3. Restart `ai-service`. Nothing else in the system changes.

This is what lets the project ship today with pretrained/demo adapters and be upgraded
later with custom-trained models, without a rewrite.

## Database strategy

The Prisma schema is written against PostgreSQL (the production target, provisioned via
`docker/docker-compose.yml`). For local development without Docker/Postgres installed,
the same schema can be pointed at a local SQLite file by changing one `.env` variable —
see [`database.md`](./database.md).

## Real-time transport

WebSocket (`ws`) is used instead of Server-Sent Events because the dashboard also needs
to send lightweight client → server messages (e.g. subscribing to a specific camera's
room). Events are typed and documented in [`api.md`](./api.md).
