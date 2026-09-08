AI Surveillance & Early Threat Detection System

A modular AI-powered CCTV surveillance platform for continuous activity monitoring and
early threat detection. It combines real object detection, geometry-driven action heuristics, templated scene captioning, and
**temporal activity analysis for potential threat/escalation prediction** with a
real-time administrator dashboard.


Technology stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, SWR
- **Backend:** Node.js, Express, TypeScript, Prisma ORM, JWT auth + bcrypt, WebSocket (`ws`), Zod
- **AI service:** Python 3.12, FastAPI, Ultralytics YOLOv8 (real object detection),
  geometry-driven demo heuristics for action recognition, templated captioning, a
  transparent rule-based threat scorer
- **Database:** SQLite (local dev default, zero-config) / PostgreSQL (Docker/production) — one Prisma schema, see [`docs/database.md`](docs/database.md)
- **Real-time:** WebSocket event stream (not polling)




Academic/final-year project — add a license here if required by your institution.
