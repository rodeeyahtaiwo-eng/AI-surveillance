# frontend

The administrator dashboard: Next.js (App Router) + TypeScript + Tailwind CSS. Talks
only to the backend REST API + WebSocket — never directly to the database or ai-service.
See [`../docs/architecture.md`](../docs/architecture.md).

## Setup

```bash
cd frontend
npm install            # or `npm install` from the repo root (npm workspaces)
copy .env.example .env.local
```

## Running

```bash
npm run dev             # http://localhost:3000
```

Requires the backend running at the URL in `.env.local` (`NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_WS_URL`) — see `../backend/README.md`.

## Testing / building

```bash
npm test                # Jest + React Testing Library (component tests)
npm run typecheck       # tsc --noEmit
npm run build            # production build
```

## Pages

| Route | Purpose |
|---|---|
| `/login` | Admin sign-in |
| `/dashboard` | Stat cards, threat activity chart, live camera previews, recent incidents |
| `/monitoring` | Multi-camera live view |
| `/cameras` | Camera CRUD |
| `/alerts` | Alert list + review actions (mark reviewed / dismiss / escalate) |
| `/incidents`, `/incidents/[id]` | Incident list + detail (evidence, timeline, AI description, review) |
| `/analytics` | Filterable charts (date/camera/severity) |
| `/users` | Signed-in admin profile (multi-admin management not implemented) |
| `/settings` | Read-only view of threat thresholds, notification provider, AI service config |

Every value sourced from a demo/simulated pipeline run is badged `DEMO` — see
[`../docs/demo.md`](../docs/demo.md).
