# Deploying AgroSphere

AgroSphere is a single Python service that serves both the API and the static
frontend, so it deploys anywhere that can run a container or a Python process.
There is no build step and no separate frontend host.

## 1. Required configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AGROSPHERE_ENV` | yes (prod) | `development` | Set to `production` on a real host |
| `AGROSPHERE_SECRET_KEY` | **yes in production** | none | Signs session tokens. 32+ chars |
| `AGROSPHERE_DATABASE_URL` | no | SQLite file | `postgresql+psycopg://user:pass@host:5432/db` |
| `PORT` | no | `8000` | Listen port (most platforms set this) |
| `HOST` | no | `0.0.0.0` | Bind address |
| `AGROSPHERE_WORKERS` | no | `1` | Worker processes |
| `AGROSPHERE_CORS` | no | none (same-origin) | Comma-separated allowed origins |
| `AGROSPHERE_SEED_ON_STARTUP` | no | `false` | Create the demo dataset on first boot |
| `AGROSPHERE_TOKEN_TTL_SECONDS` | no | `43200` (12h) | Session lifetime |

Generate a signing key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

In `AGROSPHERE_ENV=production` the app **refuses to start** if the key is
missing or shorter than 32 characters, and it disables `/docs`, `/redoc` and
`/openapi.json`. This is intentional: a default signing key would let anyone
forge a super-admin token.

## 2. Run with Docker (recommended)

```bash
docker build -t agrosphere .

docker run -d --name agrosphere \
  -p 8000:8000 \
  -e AGROSPHERE_ENV=production \
  -e AGROSPHERE_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e AGROSPHERE_SEED_ON_STARTUP=true \
  -v agrosphere_data:/app/backend \
  agrosphere
```

The image runs as an unprivileged user (`agrosphere`, uid 10001) and ships a
`HEALTHCHECK` against `/api/health`.

## 3. Run with Docker Compose (web + PostgreSQL)

```bash
export AGROSPHERE_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
export POSTGRES_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
docker compose up --build
```

Compose starts PostgreSQL with a persistent volume, waits for it to be healthy,
then starts the web container pointed at it. Set `AGROSPHERE_SEED_ON_STARTUP=false`
for a real deployment so demo accounts are not created.

## 4. Run without Docker

```bash
pip install -r backend/requirements.txt

export AGROSPHERE_ENV=production
export AGROSPHERE_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
export AGROSPHERE_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/agrosphere"

python -m backend.app.seed        # once, to create the demo dataset
python -m backend.app.server      # serves API + frontend on $PORT
```

Put a TLS-terminating proxy (nginx, Caddy, or the platform's load balancer) in
front. The app already trusts forwarded headers.

## 5. Platform notes

Because the service reads `PORT` and binds `0.0.0.0`, it runs on the common
PaaS providers without a Dockerfile:

- **Render / Railway / Fly.io**: point the build at `backend/requirements.txt`
  and the start command at `python -m backend.app.server`. Attach a managed
  PostgreSQL and set `AGROSPHERE_DATABASE_URL`. Fly.io needs `internal_port`
  set to your `PORT`.
- **Heroku-style buildpacks**: add a `Procfile` containing
  `web: python -m backend.app.server`.
- **Kubernetes**: the image is stateless apart from the database, so run it as
  a `Deployment` with a readiness probe on `/api/health`. Use a `Secret` for
  `AGROSPHERE_SECRET_KEY` and do not enable seeding.
- **Bare VM / systemd**: use the command in section 4 behind nginx.

## 6. Scaling and state

The service is stateless once the database is external. Two caveats:

- **Multiple workers or replicas require a shared database and a fixed
  `AGROSPHERE_SECRET_KEY`.** SQLite plus `AGROSPHERE_WORKERS>1` will corrupt
  data; the app does not guard against this, so do not combine them.
- Session tokens are signed, not stored, so any replica can validate any token
  as long as the key matches.

## 7. Health, logs and operations

- **Health:** `GET /api/health` → `{"status":"ok", ...}`
- **Logs:** structured uvicorn access logs on stdout. Set
  `AGROSPHERE_LOG_LEVEL` to `warning` to quiet them.
- **Audit trail:** every privileged action is written to a hash-chained
  `audit_events` table. Verify integrity from the Super Admin view or via
  `verify_audit_chain()`.

## 8. CI

`.github/workflows/ci.yml` runs three jobs on every push:

1. **test** — seeds a fresh database, starts the server, runs `scripts/e2e_test.py`.
2. **docker** — builds the image, boots it, and runs the same suite against it.
3. **config-guard** — asserts production refuses a missing or weak signing key.

## 9. Post-deploy checklist

- [ ] `AGROSPHERE_SECRET_KEY` is a unique 32+ character random value, stored in
      a secret manager, not in git.
- [ ] `AGROSPHERE_ENV=production` so docs endpoints are off.
- [ ] Database is PostgreSQL (or another server DB), not a container-local SQLite file.
- [ ] `AGROSPHERE_SEED_ON_STARTUP=false` and the demo accounts are removed, or
      the passwords changed.
- [ ] `AGROSPHERE_CORS` set to your real origin if the frontend is ever hosted
      separately; leave unset for same-origin.
- [ ] TLS enabled at the proxy, backups scheduled for the database volume.
- [ ] `GET /api/health` returns 200 and the container health status is `healthy`.
