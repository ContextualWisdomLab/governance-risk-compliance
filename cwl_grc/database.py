"""Engine and session factory for the GRC product store."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cwl_grc.migrations import apply_schema_migrations, install_integrity_guards
from cwl_grc.models import Base


DEFAULT_CONNECT_TIMEOUT_SECONDS = 3


def build_engine(
    database_url: str,
    *,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
) -> Engine:
    """Build a SQLAlchemy engine, sharing one in-memory SQLite connection when asked."""
    if (
        isinstance(connect_timeout_seconds, bool)
        or not isinstance(connect_timeout_seconds, int)
        or connect_timeout_seconds <= 0
    ):
        raise ValueError("Database connect timeout must be a positive integer.")
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("postgresql"):
        return create_engine(
            database_url,
            connect_args={"connect_timeout": connect_timeout_seconds},
        )
    return create_engine(database_url)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create or upgrade tables and return a guarded product session factory."""
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    apply_schema_migrations(engine)
    install_integrity_guards(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_dependency(
    factory: sessionmaker[Session],
    telemetry: Any | None = None,
) -> Iterator[Session]:
    """Yield a request-scoped session and roll back on error."""
    session = factory()
    started_at = time.perf_counter()
    outcome = "commit"
    try:
        yield session
        session.commit()
    except Exception:
        outcome = "rollback"
        session.rollback()
        raise
    finally:
        if telemetry is not None:
            telemetry.record_database_transaction(
                session.bind.dialect.name,
                outcome,
                time.perf_counter() - started_at,
            )
        session.close()
