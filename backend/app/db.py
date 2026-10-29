"""Database engine, session factory and schema creation helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

DATABASE_URL = settings.database_url

_is_sqlite = DATABASE_URL.startswith("sqlite")
# check_same_thread is a SQLite-only concern; pool_pre_ping keeps long-lived
# connections healthy on managed databases that silently drop idle sessions.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # create_all adds missing tables but not missing columns on existing ones.
    from .migrations import run_migrations

    run_migrations(engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
