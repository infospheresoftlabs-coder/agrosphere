#!/usr/bin/env bash
# Start AgroSphere: install deps if needed, seed once, then serve.
set -e
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"

if ! python3 -c "import fastapi, uvicorn, sqlalchemy, email_validator" 2>/dev/null; then
  echo "Installing dependencies…"
  pip install -q -r backend/requirements.txt
fi

if [ ! -f backend/agrosphere.db ]; then
  echo "Seeding demo data…"
  python3 -m backend.app.seed
fi

echo "AgroSphere listening on http://0.0.0.0:${PORT}"
exec python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}"
