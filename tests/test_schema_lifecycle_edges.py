"""Edge and branch contracts for explicit schema lifecycle controls."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

import cwl_grc.database as database_module
from cwl_grc import create_app
from cwl_grc.cli import _database_command, main
from cwl_grc.migrations import install_integrity_guards


def test_application_rejects_unknown_schema_mode() -> None:
    """The runtime never guesses whether it owns database schema mutation."""
    with pytest.raises(ValueError, match="schema mode"):
        create_app(database_url="sqlite://", schema_mode="automatic")


@pytest.mark.parametrize(
    "values",
    [
        {"sslmode": "prefer"},
        {"application_name": " cwl-grc"},
        {"connect_timeout_seconds": True},
        {"statement_timeout_ms": 0},
        {"pool_size": "5"},
        {"max_overflow": True},
        {"max_overflow": -1},
    ],
)
def test_postgresql_settings_reject_ambiguous_or_unbounded_values(
    values: dict[str, Any],
) -> None:
    """Every connection and pool boundary is a typed finite policy value."""
    with pytest.raises(ValueError):
        database_module.PostgresEngineSettings(**values)


def test_database_cli_reports_unsupported_dialect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator commands return a deterministic next action for unsupported stores."""
    assert main(["database", "check", "--database-url", "mysql://db.example/grc"]) == 1
    payload = capsys.readouterr().out
    assert "Unsupported GRC database dialect" in payload
    assert "Correct the command input or runtime configuration" in payload


def test_database_command_rejects_unexpected_parser_state() -> None:
    """A parser state outside migrate/check is a typed non-success result."""
    namespace = argparse.Namespace(
        database_command="unexpected",
        database_url="sqlite://",
    )
    assert _database_command(namespace) == 2


def test_postgresql_rejects_ambiguous_or_mismatched_sslmode() -> None:
    """The URL cannot override or multiply the reviewed TLS policy."""
    with pytest.raises(ValueError, match="one exact value"):
        database_module.build_engine(
            "postgresql+psycopg://grc@example.test/grc?"
            "sslmode=verify-full&sslmode=verify-full"
        )
    with pytest.raises(ValueError, match="verify-full"):
        database_module.build_engine(
            "postgresql+psycopg://grc@example.test/grc?sslmode=require"
        )


def test_postgresql_default_tls_policy_may_supply_omitted_query_value() -> None:
    """The resource owner may omit the URL value without weakening verify-full."""
    engine = database_module.build_engine("postgresql+psycopg://grc@example.test/grc")
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool.size() == database_module.PostgresEngineSettings().pool_size
    finally:
        engine.dispose()


def test_postgresql_loopback_profile_accepts_localhost() -> None:
    """The explicit insecure CI profile recognizes the loopback hostname only."""
    settings = database_module.PostgresEngineSettings(
        sslmode="disable",
        allow_insecure_loopback=True,
    )
    engine = database_module.build_engine(
        "postgresql+psycopg://grc@localhost/grc?sslmode=disable",
        postgres_settings=settings,
    )
    engine.dispose()


def test_runtime_rejects_schema_missing_required_table(tmp_path: Path) -> None:
    """Migration receipts cannot hide an incomplete or damaged table set."""
    database_url = f"sqlite:///{tmp_path / 'missing-table.sqlite'}"
    database_module.migrate_database(database_url)
    engine = database_module.build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE policy_document"))
        with pytest.raises(database_module.SchemaCompatibilityError, match="required tables"):
            database_module.assert_schema_compatible(engine)
    finally:
        engine.dispose()


def test_runtime_rejects_schema_missing_required_column(tmp_path: Path) -> None:
    """Migration receipts cannot hide a table with a missing required column."""
    database_url = f"sqlite:///{tmp_path / 'missing-column.sqlite'}"
    database_module.migrate_database(database_url)
    engine = database_module.build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE control_framework DROP COLUMN source_url"))
        with pytest.raises(database_module.SchemaCompatibilityError, match="required columns"):
            database_module.assert_schema_compatible(engine)
    finally:
        engine.dispose()


def test_integrity_guard_installer_accepts_engine(tmp_path: Path) -> None:
    """The public guard installer remains idempotent for engine-owning callers."""
    database_url = f"sqlite:///{tmp_path / 'guard-engine.sqlite'}"
    database_module.migrate_database(database_url)
    engine = database_module.build_engine(database_url)
    try:
        install_integrity_guards(engine)
    finally:
        engine.dispose()


class _ScalarResult:
    """Minimal scalar result used to exercise PostgreSQL migration locking."""

    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        """Return the configured advisory-lock result."""
        return self._value


class _FakeConnection:
    """Minimal PostgreSQL connection boundary for migration-lock tests."""

    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.parameters: dict[str, int] | None = None

    def execute(self, _statement: object, parameters: dict[str, int]) -> _ScalarResult:
        """Capture the advisory-lock parameters and return one scalar result."""
        self.parameters = parameters
        return _ScalarResult(self.acquired)


class _BeginContext:
    """Context manager returning one fake PostgreSQL connection."""

    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        """Return the fake transaction connection."""
        return self.connection

    def __exit__(self, *_args: object) -> None:
        """Close the fake transaction context without suppressing failures."""
        return None


class _FakeEngine:
    """Minimal engine exposing a caller-owned transaction context."""

    def __init__(self, acquired: bool) -> None:
        self.connection = _FakeConnection(acquired)

    def begin(self) -> _BeginContext:
        """Return the fake transaction context."""
        return _BeginContext(self.connection)


def test_postgresql_migration_acquires_lock_before_schema_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single migration writer holds one lock through schema and seed writes."""
    calls: list[str] = []
    engine = _FakeEngine(acquired=True)
    monkeypatch.setattr(
        database_module.Base.metadata,
        "create_all",
        lambda _connection: calls.append("create_all"),
    )
    monkeypatch.setattr(
        database_module,
        "apply_schema_migrations",
        lambda _connection: calls.append("migrations"),
    )
    monkeypatch.setattr(
        database_module,
        "install_integrity_guards",
        lambda _connection: calls.append("guards"),
    )
    monkeypatch.setattr(
        database_module,
        "_seed_reference_data",
        lambda _connection: calls.append("seed"),
    )

    database_module._migrate_engine(engine)  # type: ignore[arg-type]

    assert engine.connection.parameters == {
        "lock_key": database_module.POSTGRESQL_MIGRATION_LOCK_KEY
    }
    assert calls == ["create_all", "migrations", "guards", "seed"]


def test_postgresql_migration_fails_when_lock_is_owned_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrent migration writer fails closed before touching schema state."""
    engine = _FakeEngine(acquired=False)
    monkeypatch.setattr(
        database_module.Base.metadata,
        "create_all",
        lambda _connection: pytest.fail("DDL must not run without the lock"),
    )

    with pytest.raises(database_module.SchemaCompatibilityError, match="advisory lock"):
        database_module._migrate_engine(engine)  # type: ignore[arg-type]
