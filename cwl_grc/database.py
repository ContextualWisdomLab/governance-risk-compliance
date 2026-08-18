"""Engine and session factory for the GRC product store."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cwl_grc.models import Base


def build_engine(database_url: str) -> Engine:
    """Build a SQLAlchemy engine, sharing one in-memory SQLite connection when asked."""
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create tables and return a session factory bound to the product store."""
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_dependency(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a request-scoped session and roll back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
