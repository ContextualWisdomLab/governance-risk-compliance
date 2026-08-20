"""Engine policy, explicit schema lifecycle, and sessions for the GRC store."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from ipaddress import ip_address

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cwl_grc.migrations import (
    POLICY_INTEGRITY_MIGRATION,
    apply_schema_migrations,
    install_integrity_guards,
)
from cwl_grc.models import Base


POSTGRESQL_DRIVER = "postgresql+psycopg"
POSTGRESQL_MIGRATION_LOCK_KEY = 0x43574C475243
EXPECTED_MIGRATION_KEYS = frozenset({POLICY_INTEGRITY_MIGRATION})


class SchemaCompatibilityError(RuntimeError):
    """Signal that the database cannot be served by this exact application build."""


@dataclass(frozen=True)
class PostgresEngineSettings:
    """Finite PostgreSQL connection, pool, TLS, and statement-wait policy."""

    sslmode: str = "verify-full"
    allow_insecure_loopback: bool = False
    connect_timeout_seconds: int = 5
    statement_timeout_ms: int = 30_000
    lock_timeout_ms: int = 5_000
    idle_transaction_timeout_ms: int = 60_000
    application_name: str = "cwl-grc"
    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout_seconds: int = 5
    pool_recycle_seconds: int = 300

    def __post_init__(self) -> None:
        """Reject unbounded waits, ambiguous names, and incoherent timeout ordering."""
        if self.sslmode not in {"verify-full", "disable"}:
            raise ValueError("PostgreSQL sslmode must be verify-full or disable.")
        if not self.application_name or self.application_name != self.application_name.strip():
            raise ValueError("PostgreSQL application name must be one exact non-empty value.")
        positive_values = (
            self.connect_timeout_seconds,
            self.statement_timeout_ms,
            self.lock_timeout_ms,
            self.idle_transaction_timeout_ms,
            self.pool_size,
            self.pool_timeout_seconds,
            self.pool_recycle_seconds,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in positive_values):
            raise ValueError("PostgreSQL connection and timeout bounds must be positive integers.")
        if isinstance(self.max_overflow, bool) or not isinstance(self.max_overflow, int):
            raise ValueError("PostgreSQL max overflow must be a non-negative integer.")
        if self.max_overflow < 0:
            raise ValueError("PostgreSQL max overflow must be a non-negative integer.")
        if self.lock_timeout_ms >= self.statement_timeout_ms:
            raise ValueError("PostgreSQL lock timeout must be lower than statement timeout.")


def build_engine(
    database_url: str,
    *,
    postgres_settings: PostgresEngineSettings | None = None,
) -> Engine:
    """Build a bounded SQLite or exact-psycopg PostgreSQL engine."""
    url = make_url(database_url)
    if url.drivername == "sqlite" and database_url in {"sqlite://", "sqlite:///:memory:"}:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if url.drivername == "sqlite":
        return create_engine(url)
    if url.drivername.startswith("postgresql"):
        if url.drivername != POSTGRESQL_DRIVER:
            raise ValueError("PostgreSQL URLs must use the exact postgresql+psycopg driver.")
        return _build_postgresql_engine(url, postgres_settings or PostgresEngineSettings())
    raise ValueError(f"Unsupported GRC database dialect: {url.drivername}")


def _build_postgresql_engine(
    url: URL,
    settings: PostgresEngineSettings,
) -> Engine:
    """Build one PostgreSQL engine with closed TLS and finite wait contracts."""
    host = url.host or ""
    query_sslmode = url.query.get("sslmode")
    if not isinstance(query_sslmode, (str, type(None))):
        raise ValueError("PostgreSQL sslmode must be one exact value.")
    if query_sslmode is not None and query_sslmode != settings.sslmode:
        raise ValueError("PostgreSQL URL sslmode must match the engine policy.")
    if settings.sslmode != "verify-full":
        if not settings.allow_insecure_loopback or not _host_is_loopback(host):
            raise ValueError("PostgreSQL TLS may be disabled only for an explicit loopback test.")
    elif query_sslmode not in {None, "verify-full"}:
        raise ValueError("Remote PostgreSQL requires sslmode=verify-full.")

    options = " ".join(
        (
            f"-c statement_timeout={settings.statement_timeout_ms}",
            f"-c lock_timeout={settings.lock_timeout_ms}",
            (
                "-c idle_in_transaction_session_timeout="
                f"{settings.idle_transaction_timeout_ms}"
            ),
        )
    )
    engine = create_engine(
        url,
        connect_args={
            "sslmode": settings.sslmode,
            "connect_timeout": settings.connect_timeout_seconds,
            "application_name": settings.application_name,
            "options": options,
        },
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        isolation_level="READ COMMITTED",
    )
    engine.dialect.isolation_level = "READ COMMITTED"
    return engine


def _host_is_loopback(host: str) -> bool:
    """Return whether a database hostname is explicitly loopback-only."""
    if host.casefold() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def migrate_database(
    database_url: str,
    *,
    postgres_settings: PostgresEngineSettings | None = None,
) -> tuple[str, ...]:
    """Run the single-writer schema upgrade and return exact migration receipts."""
    engine = build_engine(database_url, postgres_settings=postgres_settings)
    try:
        _migrate_engine(engine)
        return assert_schema_compatible(engine)
    finally:
        engine.dispose()


def _migrate_engine(engine: Engine) -> None:
    """Apply DDL in one transaction and use a PostgreSQL advisory migration lock."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            acquired = connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": POSTGRESQL_MIGRATION_LOCK_KEY},
            ).scalar_one()
            if acquired is not True:
                raise SchemaCompatibilityError(
                    "Another PostgreSQL schema migration owns the advisory lock."
                )
        Base.metadata.create_all(connection)
        apply_schema_migrations(connection)
        install_integrity_guards(connection)


def assert_schema_compatible(engine: Engine) -> tuple[str, ...]:
    """Reject missing, older, or newer schemas before a runtime session is opened."""
    inspector = inspect(engine)
    if not inspector.has_table("schema_migration"):
        raise SchemaCompatibilityError(
            "The GRC schema is not initialized. Run `cwl-grc database migrate`."
        )
    expected_tables = set(Base.metadata.tables)
    missing_tables = expected_tables.difference(inspector.get_table_names())
    if missing_tables:
        raise SchemaCompatibilityError(
            "The GRC schema is behind this binary; required tables are missing."
        )
    with engine.connect() as connection:
        receipts = tuple(
            connection.execute(
                text("SELECT migration_key FROM schema_migration ORDER BY migration_key")
            ).scalars()
        )
    receipt_set = frozenset(receipts)
    missing_migrations = EXPECTED_MIGRATION_KEYS.difference(receipt_set)
    if missing_migrations:
        raise SchemaCompatibilityError(
            "The GRC schema is behind this binary; run the migration owner."
        )
    unknown_migrations = receipt_set.difference(EXPECTED_MIGRATION_KEYS)
    if unknown_migrations:
        raise SchemaCompatibilityError(
            "The GRC schema is ahead of this binary; deploy a compatible application."
        )
    return receipts


def create_session_factory(
    database_url: str,
    *,
    manage_schema: bool = True,
    postgres_settings: PostgresEngineSettings | None = None,
) -> sessionmaker[Session]:
    """Return a session factory after explicit migration or fail-closed runtime check."""
    engine = build_engine(database_url, postgres_settings=postgres_settings)
    try:
        if manage_schema:
            _migrate_engine(engine)
        assert_schema_compatible(engine)
    except Exception:
        engine.dispose()
        raise
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
