# backend

Express + TypeScript API: authentication, camera/alert/incident CRUD, the inference
ingestion API (ai-service → backend), the backend-owned Threat Engine, WebSocket
real-time events, and the Prisma-backed database layer. See
[`../docs/api.md`](../docs/api.md) and [`../docs/architecture.md`](../docs/architecture.md).

## Setup

```bash
cd backend
npm install            # or `npm install` from the repo root (npm workspaces)
copy .env.example .env
npm run db:generate
npm run db:push         # creates dev.db (SQLite) and applies the schema (non-interactive)
npm run db:seed        # creates the admin user + demo cameras
```

## Running

```bash
npm run dev             # http://localhost:4000, WebSocket at /ws
```

## Testing

```bash
npm test
```

Tests run against a separate SQLite file (`tests/test.db`, see `jest.config.js` +
`tests/globalSetup.ts`) so they never touch your local `dev.db`.

## Database

Local dev defaults to SQLite (see `database/schema.prisma`). For PostgreSQL (Docker /
production), see [`../docs/database.md`](../docs/database.md).

## Key modules

| Path | Purpose |
|---|---|
| `src/routes/`, `src/controllers/`, `src/services/` | REST API layers |
| `src/services/threatEngine.service.ts` + `src/config/threatConfig.ts` | The Threat Engine — score → severity → Alert/Incident |
| `src/services/notification/` | Notification provider abstraction (dev LOG provider wired; email/SMS/push are interfaces, not implemented) |
| `src/websocket/` | Real-time event broadcast to the dashboard |
| `src/middleware/` | Auth (JWT), ingest-key auth (service-to-service), validation, error handling |
