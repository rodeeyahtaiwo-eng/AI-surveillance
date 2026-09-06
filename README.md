# AI Surveillance & Early Threat Detection System

A modular AI-powered CCTV surveillance platform for continuous activity monitoring and
early threat detection — built as a final-year project. It combines real object
detection, geometry-driven action heuristics, templated scene captioning, and
**temporal activity analysis for potential threat/escalation prediction** with a
real-time administrator dashboard.

> **Framing note:** this system does not, and does not claim to, predict the future. It
> analyzes sequences of detected events over time and produces a transparent, rule-based
> risk score with a human-readable rationale — see [`docs/ai-pipeline.md`](docs/ai-pipeline.md).

## Project status: all 18 phases implemented and verified

Every service below was actually run in this project's dev environment — not just
written. **220/220 automated tests pass** (21 backend, 42 frontend, 151 ai-service, 6
video-processing), and the full pipeline was exercised live end-to-end: a scripted DEMO
escalation posted through `ai-service` correctly produced a LOW alert, then MEDIUM, then
a HIGH alert **and** a backend-created Incident, then CRITICAL — visible on the
dashboard via the live WebSocket feed. Real YOLOv8 was also verified separately: it
loaded its pretrained weights and ran inference on a frame.

| Area | Status |
|---|---|
| Architecture, docs, config | ✅ |
| Frontend dashboard (10 pages) | ✅ Build passes, 42/42 tests pass |
| Backend API, auth, DB, WebSocket | ✅ 21/21 tests pass |
| Camera management | ✅ |
| Video/demo streaming (webcam/file/RTSP ingestion) | ✅ 6/6 tests pass, verified live against ai-service |
| AI service (real YOLOv8 detection; demo action/caption adapters) | ✅ verified live — firearm detection was evaluated and removed, see Limitations |
| Temporal threat analysis + alert/incident engine | ✅ Verified live end-to-end |
| Notifications | ✅ Dev `LOG` provider wired; real email/SMS/push are interfaces only (see Limitations) |
| Analytics | ✅ Filterable charts backed by real aggregation queries |
| Docker/deployment | ⚠️ Written, YAML-validated, **not build-tested** (no Docker in this dev environment — see Limitations) |

## Architecture

```
frontend (Next.js) ⇄ backend (Express + WebSocket) ⇄ PostgreSQL/SQLite
                              ▲
                              │ HTTP (results in, service-to-service key)
                        ai-service (FastAPI, pluggable adapters)
                              ▲
                              │ HTTP (frames in)
                     video-processing (RTSP / webcam / demo file)
```

Full detail: [`docs/architecture.md`](docs/architecture.md).

## Technology stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, SWR
- **Backend:** Node.js, Express, TypeScript, Prisma ORM, JWT auth + bcrypt, WebSocket (`ws`), Zod
- **AI service:** Python 3.12, FastAPI, Ultralytics YOLOv8 (real object detection),
  geometry-driven demo heuristics for action recognition, templated captioning, a
  transparent rule-based threat scorer
- **Database:** SQLite (local dev default, zero-config) / PostgreSQL (Docker/production) — one Prisma schema, see [`docs/database.md`](docs/database.md)
- **Real-time:** WebSocket event stream (not polling)

## AI model strategy — what's real vs. demo

| Capability | Status | Detail |
|---|---|---|
| Person / vehicle detection | **Real** — YOLOv8n, COCO-pretrained | CPU-capable; verified loading weights and running inference in this project |
| Weapon/firearm detection | **Removed (Phase 2V)** | Evaluated across several phases; real testing found it firing on real knife frames — see [`docs/phase2v-firearm-removal.md`](docs/phase2v-firearm-removal.md). Knife detection remains available via the general YOLOv8n detector's own `knife` class. |
| Action recognition (walking/fighting/etc.) | **Demo heuristic over real geometry** | Computes real bounding-box proximity/speed from real detections, but the label-mapping rule is hand-written, not a trained model |
| Video captioning | **Demo (templated)** | Composes a sentence from object counts + action label; not a vision-language model |
| Threat/escalation scoring | **Real, transparent rule-based engine** | Fully traceable weighted score + rationale; not a black box; not a claim of predictive certainty |

Every AI result carries a `mode: "REAL" \| "DEMO"` flag and is badged accordingly on the
dashboard — see [`docs/demo.md`](docs/demo.md).

## Repository layout

```
frontend/            Next.js admin dashboard
backend/              Express API, Prisma, WebSocket, auth, Threat Engine
ai-service/           Python FastAPI AI inference pipeline
video-processing/     Camera/video ingestion + frame sampling
database/             Prisma schema (shared source of truth)
models/                YOLOv8 weights (git-ignored) — see models/README.md
docker/                docker-compose + per-service Dockerfiles
docs/                  Architecture, setup, AI pipeline, database, API, demo docs
```

Each service also has its own `README.md` with exact run/test commands.

## Installation & running — quick start

```bash
git clone <this-repo>
cd AIsurveillance
npm install                                  # frontend + backend

cd backend && copy .env.example .env && npm run db:push && npm run db:seed && npm run dev
# in another terminal:
cd frontend && copy .env.example .env.local && npm run dev
```

Open http://localhost:3000, sign in with `ADMIN_EMAIL`/`ADMIN_PASSWORD` from
`backend/.env` (defaults: `admin@example.com` / `ChangeMe123!`). See
[`docs/setup.md`](docs/setup.md) for the AI service, video-processing, Docker, and full
verification commands — every command there has actually been run in this project.

## Seeing the full pipeline work without any camera hardware

```bash
cd ai-service && py -3.12 -m venv venv && venv\Scripts\pip install -r requirements.txt && copy .env.example .env && venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Then, with a camera ID from the dashboard's Cameras page:
```bash
curl -X POST "http://localhost:8000/demo/simulate-scenario?camera_id=<id>"
```

Watch the Alerts/Incidents pages update live over ~16 seconds as it plays LOW → MEDIUM →
HIGH → CRITICAL, exactly the escalation example in [`docs/ai-pipeline.md`](docs/ai-pipeline.md).
Every event is clearly badged **DEMO**. See [`docs/demo.md`](docs/demo.md).

## Environment variables

Every service has a `.env.example` — copy it to `.env` (or `.env.local` for frontend)
and never commit the real file. Key ones:

| Var | Service | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | SQLite file path or Postgres connection string |
| `JWT_SECRET` | backend | Session token signing secret |
| `INGEST_API_KEY` | backend, ai-service | Shared secret for ai-service → backend calls |
| `AI_SERVICE_URL` | backend | Where to reach ai-service (for health checks) |
| `BACKEND_URL` | ai-service | Where to POST inference results |
| `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` | frontend | Backend endpoints (exposed to the browser — no secrets here) |

## Connecting a real CCTV camera

Add it via the Cameras page with an RTSP URL (`rtsp://user:pass@host:port/stream`).
Credentials are stored server-side only, never sent to or rendered in frontend code.
Then run `video-processing` pointed at it: `--source rtsp --url <the same URL>`. This
path is implemented but **untested against real hardware** in this project (no physical
camera was available) — see Limitations.

## Limitations (read before demoing)

- **Firearm detection was removed (Phase 2V)** — a single-class "Gun" detector was
  built and evaluated across several phases, but real testing found it firing on real
  knife frames at 0.74–0.76 confidence, and the accumulated evidence never established
  reliable firearm-vs-non-firearm discrimination. This is not a claim that firearm
  detection is impossible, nor that knives and firearms are now reliably distinguished.
  Knife detection (general YOLOv8n's own `knife` class, with persistence + person-context
  scoring) remains the supported weapon-adjacent signal. See
  [`docs/phase2v-firearm-removal.md`](docs/phase2v-firearm-removal.md).
- **Action recognition and captioning are demo/heuristic**, not trained models — the
  geometric inputs can be real (from real YOLOv8 detections), but the label-assignment
  rules and sentence templates are hand-written.
- **Threat/escalation scoring is a transparent rule-based heuristic**, not a claim of
  predictive certainty, and not (yet) validated against real incident data — there is
  none available.
- **RTSP/real-camera ingestion is implemented but untested against physical hardware** —
  verified with a synthetic file source and the scripted demo scenario instead.
- **Docker Compose is written and YAML-validated but not build-tested** — this dev
  environment had no Docker daemon available. Each Dockerfile follows the same commands
  verified manually per-service; run `docker compose up --build` as a smoke test before
  relying on it for a demo.
- **Real email/SMS/push notifications are interfaces only** — only the development `LOG`
  provider (safe console logging) is wired up; see `backend/src/services/notification/`.
- **Multi-admin user management is not implemented** — single admin account (seeded),
  no invite/create/deactivate UI or API yet.
- No real CCTV footage or trained surveillance-specific models were used anywhere in
  this project — every "real" claim above refers specifically to YOLOv8's pretrained
  COCO object detection and the transparent rule-based threat scoring, nothing more.

## License

Academic/final-year project — add a license here if required by your institution.
