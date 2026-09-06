# API Reference

Base URL: `http://localhost:4000/api` (configurable via `backend/.env`, `PORT`). All
bodies are JSON; validated with Zod — a validation failure returns `400` with
`{ error: "Validation failed", issues: [{ path, message }] }`. Other errors return
`{ error: string, code?: string }`.

## Auth

All routes below require `Authorization: Bearer <token>` **except** `POST /auth/login`
and the `/inference/*` routes (which use a separate service-to-service secret instead —
see "Inference ingestion" below).

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/auth/login` | `{ email, password }` | Returns `{ token, user }`. Rate-limited (20/15min). |
| POST | `/auth/logout` | — | Stateless (JWT) — client just discards the token. |
| GET | `/auth/me` | — | Returns `{ user }` for the current token. |

## Cameras

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/cameras` | — | List all cameras. |
| POST | `/cameras` | `{ name, location, streamUrl, description?, status?, isDemo? }` | `status` defaults `OFFLINE`. |
| GET | `/cameras/:id` | — | 404 if missing. |
| PUT | `/cameras/:id` | Partial of the create body | |
| DELETE | `/cameras/:id` | — | 204 on success. |

`status` ∈ `ONLINE \| OFFLINE \| ERROR \| PROCESSING`.

## Alerts

| Method | Path | Query/Body | Notes |
|---|---|---|---|
| GET | `/alerts` | `?severity=&status=&cameraId=&limit=` | Alerts are created by the Threat Engine, not directly by an admin. |
| GET | `/alerts/:id` | — | Includes `camera`, `action`, `incident`, `notifications`. |
| PATCH | `/alerts/:id` | `{ status }` | `status` ∈ `NEW \| REVIEWED \| DISMISSED \| ESCALATED`. Broadcasts `alert.updated`. |

`severity` ∈ `LOW \| MEDIUM \| HIGH \| CRITICAL`.

## Incidents

| Method | Path | Query/Body | Notes |
|---|---|---|---|
| GET | `/incidents` | `?severity=&reviewStatus=&limit=` | |
| GET | `/incidents/:id` | — | Includes `alerts` (with `camera`, `action`) and `videoSegments`. |
| PATCH | `/incidents/:id` | `{ reviewStatus }` | `reviewStatus` ∈ `UNREVIEWED \| UNDER_REVIEW \| CONFIRMED \| DISMISSED`. Broadcasts `incident.updated`. |

## Analytics

| Method | Path | Query | Notes |
|---|---|---|---|
| GET | `/analytics/overview` | — | Dashboard stat cards: `totalCameras`, `camerasOnline`, `activeAlerts`, `incidentsToday`, `threatLevelSummary`, `recentIncidents`. |
| GET | `/analytics` | `?from=&to=&cameraId=&severity=&eventType=` (ISO datetimes) | `alertsOverTime`, `incidentsByType`, `incidentsBySeverity`, `detectionCounts`, `cameraActivity`, `reviewStats`. |

## System

| Method | Path | Notes |
|---|---|---|
| GET | `/system/status` | `{ database: {ok}, aiService: {reachable}, camerasOnline, activeAlerts, timestamp }`. Live-pings ai-service's `/health`. |
| GET | `/system/settings` | Read-only: current threat thresholds, notification provider, ai-service URL. No secrets. |

## Inference ingestion (service-to-service, not user auth)

Called by `ai-service`, never by the frontend/browser. Guarded by
`x-ingest-key: <INGEST_API_KEY>` (must match `backend/.env`'s `INGEST_API_KEY`), not a
user JWT.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/inference/detections` | `{ cameraId, mode, detections: [{objectLabel, confidence, boundingBox, frameTimestamp}] }` | Persists each detection, broadcasts `detection.created` per row. |
| POST | `/inference/actions` | `{ cameraId, mode, label, confidence, description?, windowStart, windowEnd, threatScore, rationale? }` | Persists the action, broadcasts `action.detected`, then runs the **Threat Engine** (`src/services/threatEngine.service.ts`): maps `threatScore` → severity (`src/config/threatConfig.ts`), and if ≥ LOW, creates an `Alert` (broadcasts `alert.created`); if HIGH/CRITICAL, also creates an `Incident` (broadcasts `incident.created`) and dispatches a notification (dev `LOG` provider). |

Datetime fields accept both `...Z` and `...+00:00` offset formats (Python's
`datetime.isoformat()`, used by ai-service, emits the latter).

## Real-time events (WebSocket)

Connect: `ws://localhost:4000/ws?token=<JWT>`. On connect the server sends
`{type: "connected"}`; ignore it. Every subsequent message is
`{ type, payload, timestamp }`:

| Event | Payload | Emitted when |
|---|---|---|
| `camera.online` / `camera.offline` | `{ cameraId }` | A camera's `status` is PUT to ONLINE/OFFLINE. |
| `detection.created` | `Detection` | ai-service reports a new detection. |
| `action.detected` | `Action` | ai-service reports a recognized action/window evaluation. |
| `alert.created` / `alert.updated` | `Alert` | Threat Engine creates an alert / an admin changes its status. |
| `incident.created` / `incident.updated` | `Incident` | A HIGH/CRITICAL alert is created / an admin changes review status. |

`system.error` is reserved (documented in the type union) but not yet emitted by any
code path.
