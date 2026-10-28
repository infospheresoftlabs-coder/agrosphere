# AgroSphere architecture

## 1. Layering

```
┌──────────────────────────────────────────────────────────┐
│ Frontend SPA  (vanilla ES modules, no build step)        │
│   core.js  — API client, i18n, UI primitives, offline q  │
│   app.js   — shell, hash routing, 15 role-aware views    │
└───────────────┬──────────────────────────────────────────┘
                │ fetch /api/*  (Bearer token)
┌───────────────▼──────────────────────────────────────────┐
│ FastAPI  main.py — 59 routes                             │
│   security.py   auth, token, role dependencies           │
│   services/ai.py    provider-independent analysis        │
│   services/core.py  workflow, audit, notify, payments    │
│   services/geo.py   geodesy + mission simulation         │
└───────────────┬──────────────────────────────────────────┘
                │ SQLAlchemy 2.0 ORM
┌───────────────▼──────────────────────────────────────────┐
│ Database  users, farms, fields, cases, analyses, reviews │
│ plans, costs, jobs, drones, invoices, transactions,      │
│ notifications, grievances, audit_events, media_assets,   │
│ products, knowledge_sources, feature_flags, idempotency  │
└──────────────────────────────────────────────────────────┘
```

The frontend is intentionally dependency-free ES modules so it can be served
directly by FastAPI. This keeps the whole platform runnable from a single
`uvicorn` process while remaining deployable as a separate static bundle
(Android/iOS WebViews or a native shell) because all state lives behind `/api`.

## 2. Security model

- **Passwords** are hashed with PBKDF2-HMAC-SHA256 and a per-user random salt
  (260,000 iterations). Plaintext is never stored or logged.
- **Tokens** are HMAC-SHA256 signed, carry `sub`/`role`/`exp`, and are verified on
  every request.
- **Authorisation** is enforced server-side by a `require_roles(...)` dependency.
  Hiding a button in the UI is never the control; every endpoint re-checks.
- **Audit chain**: each event stores `prev_hash` and `hash = SHA-256(payload + prev)`.
  `verify_audit_chain` re-derives the whole chain and reports the first broken link,
  so tampering with history is detectable.
- **Payments**: webhooks are HMAC-verified before being trusted; repeated calls are
  collapsed by idempotency keys; amounts are never trusted from the client.
- **Media**: uploads are validated for content type and size and are never written
  to a publicly served directory.

## 3. The workflow engine

`constants.TRANSITIONS` is the single source of truth for the state graph and
`constants.STATE_OWNER` maps each state to the role allowed to enter it.
`services.core.transition_case` validates both, rejects illegal moves with HTTP
409, rejects wrong-role moves with HTTP 403, and records a reasoned audit event.
Because the graph is data, the lifecycle is configurable without touching routes.

## 4. AI service

`services/ai.analyze()` returns a structured result:

```json
{
  "model_version": "agrosphere-vision-sim-1.0",
  "findings": [{"label": "...", "confidence": 0.88, "evidence": "...", "alternative": "..."}],
  "affected_area_pct": 4.9,
  "uncertainty": 0.12,
  "escalate": false,
  "summary": "...",
  "sources": [{"title": "...", "organization": "ICAR", "version": "..."}],
  "latency_ms": 412,
  "cost_usd": 0.0007
}
```

The default implementation is a deterministic simulator, so tests are stable and
no key is required. Setting `AGROSPHERE_AI_PROVIDER`/`AGROSPHERE_AI_API_KEY`
switches `provider_status()["mode"]` to `live`, which the UI surfaces. Findings are
always flagged `preliminary` and low-confidence results set `escalate`.

## 5. Geospatial handling

`polygon_area_acres` uses the spherical-excess formula so acreage is computed from
real coordinates rather than screen geometry. `validate_boundary` rejects
non-polygons, short rings, malformed points and out-of-range coordinates.
`simulate_mission` derives plausible telemetry from acreage and payload and always
stamps `simulated: true` with a human-readable label.

## 6. Offline-first behaviour

The client keeps a localStorage-backed mutation queue. Failed write requests are
retained and retried, and the queue length is surfaced to the user. Because the
server is the only authority on state, conflict resolution favours the server
response and re-fetches the affected resource.

## 7. Honest capability boundaries

The platform is explicit about what is real and what is simulated:

| Capability | Reality |
| --- | --- |
| Crop-health workflow, RBAC, audit, payments | Real, server-enforced |
| AI analysis | Simulated by default, pluggable to a live provider |
| Drone missions | Simulator; no physical command is issued |
| Spraying | Not implemented; blocked until hardware validation |
| Languages | Interface strings present; native review still required |

## 8. Extending the platform

1. Add models to `models.py`.
2. Add a router section in `main.py` (or split into `routers/` for larger builds).
3. Add a view in `app.js` and register it in `ROUTES` with the roles allowed.
4. Add assertions to `scripts/e2e_test.py`.

That keeps the "one module = model + endpoints + view + tests + artwork" pattern
consistent across the platform.
