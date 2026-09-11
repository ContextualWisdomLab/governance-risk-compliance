"""RED contract for one advisory-lock scope across schema and reference writes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import cwl_grc.database as database_module


class _ScalarResult:
    """Return one successful PostgreSQL advisory-lock result."""

    def scalar_one(self) -> bool:
        """Report that the migration owner acquired the advisory lock."""
        return True


class _LifecycleConnection:
    """Record migration activity performed inside one fake transaction."""

    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def execute(self, _statement: object, _parameters: object) -> _ScalarResult:
        """Record advisory-lock acquisition before returning success."""
        self.events.append("lock")
        return _ScalarResult()


class _LifecycleContext:
    """Record the exact entry and exit of the migration transaction."""

    def __init__(self, events: list[str], connection: _LifecycleConnection) -> None:
        self.events = events
        self.connection = connection

    def __enter__(self) -> _LifecycleConnection:
        """Enter the transaction before any migration-owned write."""
        self.events.append("enter")
        return self.connection

    def __exit__(self, *_args: object) -> None:
        """Record transaction exit without suppressing failures."""
        self.events.append("exit")
        return None


class _LifecycleEngine:
    """Expose one transaction whose event order is externally observable."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.connection = _LifecycleConnection(events)

    def begin(self) -> _LifecycleContext:
        """Return the one migration-owner transaction context."""
        return _LifecycleContext(self.events, self.connection)


def test_reference_bootstrap_remains_inside_advisory_lock_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema DDL and shared reference writes complete before the lock is released."""
    events: list[str] = []
    engine = _LifecycleEngine(events)
    monkeypatch.setattr(
        database_module.Base.metadata,
        "create_all",
        lambda _connection: events.append("ddl"),
    )
    monkeypatch.setattr(
        database_module,
        "apply_schema_migrations",
        lambda _connection: events.append("migrations"),
    )
    monkeypatch.setattr(
        database_module,
        "install_integrity_guards",
        lambda _connection: events.append("guards"),
    )
    monkeypatch.setattr(
        database_module,
        "_seed_reference_data",
        lambda _resource: events.append("seed"),
    )

    database_module._prepare_schema(engine)  # type: ignore[arg-type]

    assert events == [
        "enter",
        "lock",
        "ddl",
        "migrations",
        "guards",
        "seed",
        "exit",
    ]
