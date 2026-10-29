"""Lightweight, idempotent schema reconciliation for existing databases.

``Base.metadata.create_all`` creates missing *tables* but never alters an
existing one, so a column added to a model does not reach a database that is
already deployed. This module closes that gap for the additive changes this
project makes, without pulling in a full migration framework.

Each step is written to be safe to run repeatedly and on both SQLite and
PostgreSQL: it inspects the live schema and only acts when something is
missing. Anything that is not a pure addition (dropping, renaming, retyping)
does not belong here.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("agrosphere.migrations")


def _column_names(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column(engine: Engine, table: str, column: str, ddl: str) -> None:
    if column in _column_names(engine, table):
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    log.info("migration: added %s.%s", table, column)


def run_migrations(engine: Engine) -> None:
    """Bring an existing schema up to date with the current models."""
    # Credential epoch: invalidates sessions issued before a password change.
    _add_column(engine, "users", "session_epoch", "INTEGER NOT NULL DEFAULT 0")
