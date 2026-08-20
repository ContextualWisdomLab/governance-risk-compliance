"""RED contracts for explicit schema ownership and production runtime checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text

from cwl_grc import create_app
from cwl_grc.cli import main
from cwl_grc.database import (
    PostgresEngineSettings,
    SchemaCompatibilityError,
    build_engine,
    create_session_factory,
    migrate_database,
)
from cwl_grc.migrations import POLICY_INTEGRITY_MIGRATION


def _database_url(tmp_path: Path) -> str:
    """Return one isolated persistent SQLite database URL."""
    return f"sqlite:///{tmp_path / 'schema-lifecycle.sqlite'}"


def test_runtime_factory_never_initializes_a_missing_schema(tmp_path: Path) -> None:
    """A production runtime refuses an uninitialized store instead of owning DDL."""
    database_url = _database_url(tmp_path)

    with pytest.raises(SchemaCompatibilityError, match="not initialized"):
        create_session_factory(database_url, manage_schema=False)

    engine = build_engine(database_url)
    try:
        assert "policy_document" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_explicit_migration_enables_runtime_factory(tmp_path: Path) -> None:
    """One explicit migration owner prepares the schema before runtime startup."""
    database_url = _database_url(tmp_path)

    migrate_database(database_url)
    factory = create_session_factory(database_url, manage_schema=False)
    try:
        with factory() as session:
            receipts = session.execute(
                text("SELECT migration_key FROM schema_migration ORDER BY migration_key")
            ).scalars().all()
        assert receipts == [POLICY_INTEGRITY_MIGRATION]
    finally:
        factory.kw["bind"].dispose()


def test_runtime_rejects_older_schema(tmp_path: Path) -> None:
    """Deleting one required migration receipt makes runtime startup fail closed."""
    database_url = _database_url(tmp_path)
    migrate_database(database_url)
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM schema_migration WHERE migration_key = :migration_key"),
                {"migration_key": POLICY_INTEGRITY_MIGRATION},
            )
    finally:
        engine.dispose()

    with pytest.raises(SchemaCompatibilityError, match="behind"):
        create_session_factory(database_url, manage_schema=False)


def test_runtime_rejects_newer_unknown_schema(tmp_path: Path) -> None:
    """An unknown future migration receipt prevents an older binary from serving."""
    database_url = _database_url(tmp_path)
    migrate_database(database_url)
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES ('9999_future_schema', CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(SchemaCompatibilityError, match="ahead"):
        create_session_factory(database_url, manage_schema=False)


def test_database_cli_migrates_then_checks_exact_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operators own schema changes through explicit migrate and check commands."""
    database_url = _database_url(tmp_path)

    assert main(["database", "check", "--database-url", database_url]) == 1
    assert "not initialized" in capsys.readouterr().out
    assert main(["database", "migrate", "--database-url", database_url]) == 0
    assert "schema_ready" in capsys.readouterr().out
    assert main(["database", "check", "--database-url", database_url]) == 0
    assert "schema_compatible" in capsys.readouterr().out


def test_database_cli_uses_database_environment_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Migration-owner commands share the product database environment default."""
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", database_url)

    assert main(["database", "migrate"]) == 0
    assert "schema_ready" in capsys.readouterr().out
    assert main(["database", "check"]) == 0
    assert "schema_compatible" in capsys.readouterr().out


def test_application_runtime_mode_refuses_missing_schema(tmp_path: Path) -> None:
    """The API process cannot silently create production tables at startup."""
    with pytest.raises(SchemaCompatibilityError, match="not initialized"):
        create_app(
            database_url=_database_url(tmp_path),
            evidence_key=Fernet.generate_key().decode("ascii"),
            schema_mode="runtime",
        )


def test_postgresql_requires_psycopg_and_verified_tls() -> None:
    """Production PostgreSQL URLs use the reviewed driver and verify-full TLS."""
    with pytest.raises(ValueError, match=r"postgresql\+psycopg"):
        build_engine("postgresql://grc@example.test/grc")
    with pytest.raises(ValueError, match="verify-full"):
        build_engine("postgresql+psycopg://grc@example.test/grc?sslmode=require")


def test_postgresql_engine_options_are_bounded_and_observable() -> None:
    """The production engine configures finite connection, pool, and SQL waits."""
    settings = PostgresEngineSettings()
    engine = build_engine(
        "postgresql+psycopg://grc@example.test/grc?sslmode=verify-full",
        postgres_settings=settings,
    )
    try:
        assert engine.pool.size() == settings.pool_size
        assert engine.pool._max_overflow == settings.max_overflow
        assert engine.pool._timeout == settings.pool_timeout_seconds
        assert engine.pool._recycle == settings.pool_recycle_seconds
        assert engine.url.drivername == "postgresql+psycopg"
        connect_args = engine.dialect.create_connect_args(engine.url)[1]
        assert connect_args["sslmode"] == "verify-full"
    finally:
        engine.dispose()


def test_postgresql_ci_may_disable_tls_only_on_loopback() -> None:
    """An explicit test profile cannot weaken TLS for a remote PostgreSQL host."""
    local_settings = PostgresEngineSettings(
        sslmode="disable",
        allow_insecure_loopback=True,
    )
    engine = build_engine(
        "postgresql+psycopg://grc@127.0.0.1/grc?sslmode=disable",
        postgres_settings=local_settings,
    )
    engine.dispose()

    with pytest.raises(ValueError, match="loopback"):
        build_engine(
            "postgresql+psycopg://grc@example.test/grc?sslmode=disable",
            postgres_settings=local_settings,
        )


def test_postgresql_timeout_order_is_validated() -> None:
    """Lock timeout remains lower than statement timeout so failures are diagnosable."""
    with pytest.raises(ValueError, match="lock timeout"):
        PostgresEngineSettings(
            lock_timeout_ms=30_000,
            statement_timeout_ms=30_000,
        )
