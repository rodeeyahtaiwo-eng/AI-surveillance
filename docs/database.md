# Database

## Strategy

The Prisma schema (`database/schema.prisma`) is the single source of truth for the data
model. It is written primarily for **PostgreSQL** (the recommended target for anything
beyond solo local development — provisioned via `docker/docker-compose.yml`).

For local development on a machine without Docker or a local Postgres install (the
default state of this project's dev environment), the same schema runs against
**SQLite** by switching two lines:

```prisma
datasource db {
  provider = "sqlite"          // was "postgresql"
  url      = env("DATABASE_URL")
}
```

and setting `DATABASE_URL="file:./dev.db"` in `backend/.env`.

Both are valid, supported configurations — pick one via `database/schema.prisma`'s
`provider` line + `backend/.env`'s `DATABASE_URL`. **The checked-in schema defaults to
SQLite** (so the project runs with zero setup beyond `npm install`); the Docker path
(`docker/docker-compose.yml`) switches it to PostgreSQL automatically at container
startup (`backend/docker-entrypoint.sh`) without touching your host checkout. Run
`npm run db:generate` / `npm run db:push` (workspace: backend) after switching by hand.
`db:push` is used rather than `db:migrate` throughout this project because no formal
migration history exists yet (`prisma migrate dev` prompts interactively for a migration
name on its very first run, which isn't appropriate for a scripted setup step) — see
`backend/package.json` for both scripts. Adopting real `prisma migrate` history with
committed migration files is a natural next step for a production deployment.

Note: enum-typed fields (status, severity, role, mode, ...) are modeled as `String`, not
Prisma's native `enum`, because SQLite doesn't support enums — this keeps one schema file
working unmodified against both providers. Allowed values are documented inline in the
schema and enforced by Zod at the API boundary (`backend/src/schemas/`). Similarly,
`Detection.boundingBox` is a JSON-encoded `String`, not Prisma's `Json` type, because
SQLite doesn't support `Json` columns either.

## Entities

| Table | Purpose |
|---|---|
| `User` | Administrator accounts (hashed password, role) |
| `Camera` | Registered camera sources (RTSP URL, webcam, or demo file), status |
| `Detection` | A single object-detection result (person/vehicle/...) tied to a camera + frame timestamp; `boundingBox` is a JSON-encoded `[x1,y1,x2,y2]` string |
| `Action` | A recognized action/activity over a short frame window, tied to a camera; carries `threatScoreHint` — the raw 0.0-1.0 score from ai-service, before the backend Threat Engine maps it to an Alert severity |
| `VideoSegment` | Reference to a stored evidence clip (path/URL, start/end time) |
| `Alert` | A generated alert (type, severity, confidence, status) |
| `Incident` | An aggregated, reviewable security event, linking detections/actions/alerts/evidence |
| `Notification` | A record of a notification dispatch attempt (channel, status) |
| `SystemEvent` | Operational events (camera online/offline, AI service errors, etc.) |

## Relationships

```
Camera 1─* Detection
Camera 1─* Action           (derived from a window of that camera's recent Detections —
                              not a formal DB relation, since the window is time-based)
Camera 1─* VideoSegment
Camera 1─* Alert
Action  1─* Alert           (an Alert is raised from one Action's threat score)
Alert   *─1 Incident        (an Incident aggregates one or more Alerts)
Incident 1─* VideoSegment    (evidence)
Alert   1─* Notification
```

See `database/schema.prisma` for exact fields, types, and cascade rules.

## Seeding

`backend/prisma/seed.ts` creates one admin user (credentials from `.env`, never hardcoded)
and, in demo mode, sample cameras — see [`demo.md`](./demo.md).
