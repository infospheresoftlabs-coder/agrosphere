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


def _database_url() -> str:
    """Resolve the database URL, normalising managed-provider formats.

    Hosting platforms (Render, Railway, Heroku, Fly) hand out bare
    ``postgres://`` or ``postgresql://`` connection strings. SQLAlchemy maps
    those to psycopg2, which is not installed, so pin the driver explicitly.
    """
    raw = (
        os.getenv("AGROSPHERE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///" + str(BACKEND_DIR / "agrosphere.db")
    ).strip()
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix) :]
    return raw


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("AGROSPHERE_ENV", "development").strip().lower())
    seed_on_startup: bool = field(default_factory=lambda: _bool("AGROSPHERE_SEED_ON_STARTUP", False))
    cors_origins: list[str] = field(default_factory=_origins)
    database_url: str = field(default_factory=_database_url)
    # Set when the app is served behind a TLS-terminating proxy, so that
    # redirects and cookie/secure behaviour are generated with the right scheme.
    behind_proxy: bool = field(default_factory=lambda: _bool("AGROSPHERE_BEHIND_PROXY", False))
    workers: int = field(default_factory=lambda: _int("AGROSPHERE_WORKERS", 1))
    # Absolute base URL used in outbound links (password-reset emails). Falls
    # back to the provider-injected URL so a managed deploy works unconfigured.
    public_base_url: str = field(
        default_factory=lambda: (
            os.getenv("AGROSPHERE_PUBLIC_BASE_URL", "").strip()
            or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        )
    )
    # Geoapify powers map tiles, forward/reverse geocoding and routing. The key
    # is a public, referrer-restricted browser key, so it is served to the
    # frontend through /api/meta; server-side calls use the same key.
    geoapify_api_key: str = field(
        default_factory=lambda: os.getenv("GEOAPIFY_API_KEY", "").strip()
    )
    # Leaflet + OpenStreetMap tiles are used when no Geoapify key is present, so
    # the map still works (minus geocoding/routing) before a key is configured.
    maps_provider: str = field(
        default_factory=lambda: (
            os.getenv("AGROSPHERE_MAPS_PROVIDER", "").strip()
            or ("geoapify" if os.getenv("GEOAPIFY_API_KEY", "").strip() else "openstreetmap")
        )
    )

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}


settings = Settings()
