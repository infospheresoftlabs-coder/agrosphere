"""Production entrypoint.

Reads host/port/worker settings from the environment so the same image can run
on any platform:

    python -m backend.app.server

Environment:
    PORT                  listen port (default 8000; most PaaS set this)
    HOST                  bind address (default 0.0.0.0)
    AGROSPHERE_WORKERS    worker processes (default 1; use >1 only with a real
                          database and a shared secret key)
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("AGROSPHERE_WORKERS", "1"))

    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=os.getenv("AGROSPHERE_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
