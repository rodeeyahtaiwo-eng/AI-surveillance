# Setup Guide

Every command below has been run and verified working in this project's dev
environment (Windows, Node 20.14, Python 3.12 via `py -3.12`, no Docker/Postgres
installed — see the root README for what that implies about defaults).

## Prerequisites

| Tool | Version used here | Check |
|---|---|---|
| Node.js | 20.14.x | `node -v` |
| npm | 10.x | `npm -v` |
| Python (ai-service, video-processing) | 3.12 via `py -3.12` — **not** a newer install like 3.14 | `py -3.12 --version` |
| Git | any recent | `git --version` |
| Docker + Docker Compose | optional, for the PostgreSQL/production-like path | `docker --version` |

**Why Python 3.12 specifically?** This machine also has Python 3.14 installed
(`python --version` resolves to it), but PyTorch/Ultralytics wheels weren't yet
available for it. `py -3.12` selects the working interpreter explicitly.

## 1. Install frontend + backend (npm workspaces)

```bash
cd AIsurveillance
npm install
```

This also runs `prisma generate` (backend's `postinstall` script).

## 2. Backend + database (SQLite by default)

```bash
cd backend
copy .env.example .env
npm run db:push          # creates dev.db and applies database/schema.prisma (non-interactive)
npm run db:seed         # creates the admin user (from .env) + 3 demo cameras
npm run dev              # http://localhost:4000
```

Verify: `curl http://localhost:4000/health` → `{"ok":true,"service":"backend"}`.

## 3. Frontend

```bash
cd frontend
copy .env.example .env.local
npm run dev               # http://localhost:3000
```

Sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`.

## 4. AI service

```bash
cd ai-service
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
venv\Scripts\python -m uvicorn app.main:app --port 8000
```

First real inference request downloads YOLOv8n's weights (~6MB) automatically. Verify:
`curl http://localhost:8000/health`.

## 5. Video processing (optional — only needed to feed real/demo video in)

```bash
cd video-processing
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
venv\Scripts\python -m src.run_camera --camera-id <a real camera id from step 2> --source file --path C:\path\to\video.mp4
```

See `video-processing/README.md` for webcam/RTSP.

## 6. Or: skip 4-5 entirely and use the scripted demo scenario

```bash
curl -X POST "http://localhost:8000/demo/simulate-scenario?camera_id=<id>"
```

See [`demo.md`](./demo.md) — this exercises the full alert/incident pipeline without
needing any video at all.

## 7. Docker (PostgreSQL / production-like path)

```bash
cd docker
copy .env.example .env    # edit secrets
docker compose --env-file .env up --build
```

This provisions Postgres, and switches `database/schema.prisma`'s provider to
`postgresql` **inside the container only** (`backend/docker-entrypoint.sh`) — your local
checkout keeps using SQLite. **Not build-tested in this project's environment** (no
Docker was available here) — the compose file's YAML was validated, and each
Dockerfile/entrypoint follows the same commands verified manually in steps 1-4 above,
but do a `docker compose up --build` smoke test before relying on it. See
`docker/docker-compose.yml`.

## Running the test suites

```bash
cd backend && npm test              # 21/21 passing
cd frontend && npm test             # 13/13 passing
cd ai-service && venv\Scripts\pytest -v     # 20/20 passing
cd video-processing && venv\Scripts\pytest -v   # 6/6 passing
```
