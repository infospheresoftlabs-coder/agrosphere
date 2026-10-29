# AgroSphere — repository guide

Modular agriculture platform for Indian farmers. FastAPI + SQLAlchemy backend,
vanilla ES-module frontend (no build step), SQLite by default, deployed to Render.

## Run locally

```bash
# Backend on the workspace port, serving the frontend as static files.
nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 12000 > /tmp/agrosphere.log 2>&1 &
```

The app is then reachable at `https://work-1-<id>.prod-runtime.all-hands.dev/`.
`AGROSPHERE_SEED_ON_STARTUP` seeds the five demo accounts (password `agro1234`):
`farmer@`, `agronomist@`, `manager@`, `operator@`, `admin@agrosphere.in`.

## Test

```bash
python3 scripts/e2e_test.py http://127.0.0.1:12000   # full HTTP suite
python3 scripts/test_auth_flows.py                   # auth + RBAC units
python3 scripts/test_users.py                        # deletion units
```

`e2e_test.py` mutates data (it purges and deletes). Run it against a throwaway
server, never against the deployed instance, and clean up probe accounts after
(`selfservice-probe-*`, `geo-outsider-*`, `del-*`).

Two geocoding assertions fail without `GEOAPIFY_API_KEY` (503 by design — see
`backend/app/services/geo.py`). That is expected in a bare sandbox.

## Layout

- `backend/app/main.py` — every route. Role gating uses `require_roles(...)`.
- `backend/app/constants.py` — `Role`, `CaseState`, `TRANSITIONS`, and the
  `STATE_OWNERS` map (which roles may move a case into a state) with
  `state_roles()`. Keep the endpoint guards and this map in agreement.
- `backend/app/services/` — `ai.py` (simulator + OpenRouter), `deletion.py`
  (FK-safe cascades), `messaging.py` (SMS/WhatsApp), `geo.py`, `weather.py`.
- `frontend/assets/js/core.js` — i18n (`STRINGS`, `setLang`, `onLanguageChange`)
  and shared DOM/modal helpers.
- `frontend/assets/js/app.js` — the shell, `ROUTES`, and one `view*` per screen.
- `frontend/assets/images/` — generative artwork. Regenerate with
  `scripts/generate_images.py`; every module key needs a matching `<name>.jpg`.

## Conventions

- Adding a UI string means adding it to every entry in `STRINGS` (nine
  languages today) plus an English fallback in `t()`.
- Adding a route means adding it to `ROUTES` with the roles allowed to see it;
  the server re-checks the same rule.
- Every mutating admin action must record an audit event.
