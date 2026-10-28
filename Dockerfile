# AgroSphere production image.
# Single stage is deliberate: the app has no build step (the frontend is plain
# ES modules served as static files), so there is nothing to compile out.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGROSPHERE_ENV=production \
    PORT=8000

WORKDIR /app

# Dependencies first so code edits do not invalidate the dependency layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/

# Run as an unprivileged user; the app only needs to read its own files and
# write to the database path, which is mounted or overridden in production.
RUN useradd --create-home --uid 10001 agrosphere \
    && chown -R agrosphere:agrosphere /app
USER agrosphere

EXPOSE 8000

# Uses the app's own health endpoint so orchestration restarts a wedged process.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import os,urllib.request,sys; \
url=f\"http://127.0.0.1:{os.getenv('PORT','8000')}/api/health\"; \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

CMD ["python", "-m", "backend.app.server"]
