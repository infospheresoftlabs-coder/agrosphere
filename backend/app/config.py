"""Environment-driven configuration.

Everything that differs between a laptop and a production host is read here so
the rest of the codebase never branches on environment variables directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _origins() -> list[str]:
    raw = os.getenv("AGROSPHERE_CORS", "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("AGROSPHERE_ENV", "development").strip().lower())
    seed_on_startup: bool = field(default_factory=lambda: _bool("AGROSPHERE_SEED_ON_STARTUP", False))
    cors_origins: list[str] = field(default_factory=_origins)
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "AGROSPHERE_DATABASE_URL", "sqlite:///" + str(BACKEND_DIR / "agrosphere.db")
        )
    )
    # Set when the app is served behind a TLS-terminating proxy, so that
    # redirects and cookie/secure behaviour are generated with the right scheme.
    behind_proxy: bool = field(default_factory=lambda: _bool("AGROSPHERE_BEHIND_PROXY", False))
    workers: int = field(default_factory=lambda: _int("AGROSPHERE_WORKERS", 1))

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}


settings = Settings()
