"""Real PostgreSQL mismatch, contention, and connection-failure acceptance tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from time import monotonic

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, TimeoutError as SqlAlchemyTimeoutError

from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog import FrameworkCode
from cwl_grc.database import (
    PostgresEngineSettings,
    SchemaCompatibilityError,
    build_engine,
    create_session_factory,
    migrate_database,
)
from cwl_grc.migrations import POLICY_INTEGRITY_MIGRATION
from cwl_grc.policy import ControlRef, author_policy, revise_policy


POSTGRESQL_URL = os.environ.get("CWL_GRC_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    POSTGRESQL_URL is None,
    reason="CWL_GRC_TEST_POSTGRES_URL selects the real PostgreSQL acceptance lane.",
)


def _database_url() -> str:
    """Return the explicit integration database URL or fail the selected lane."""
    assert POSTGRESQL_URL is not None
    return POSTGRESQL_URL


def _settings(**overrides: object) -> PostgresEngineSettings:
    """Return the explicit loopback CI policy with optional bounded overrides."""
    values: dict[str, object] = {
        "sslmode": "disable",
        "allow_insecure_loopback": True,
    }
    values.update(overrides)
    return PostgresEngineSettings(**values)  # type: ignore[arg-type]


@pytest.fixture(scope="module", autouse=True)
def migrated_postgresql_schema() -> None:
    """Ensure the shared isolated PostgreSQL service has the exact current schema."""
    if POSTGRESQL_URL is not None:
        migrate_database(_database_url(), postgres_settings=_settings())


def test_postgresql_migration_rerun_is_idempotent() -> None:
    """Repeated schema ownership preserves receipts and reference identities."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.connect() as connection:
            before = (
                connection.execute(
                    text("SELECT COUNT(*) FROM schema_migration")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM control_framework")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM control_item")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM authorization_purpose")
                ).scalar_one(),
            )
        first = migrate_database(_database_url(), postgres_settings=_settings())
        second = migrate_database(_database_url(), postgres_settings=_settings())
        with engine.connect() as connection:
            after = (
                connection.execute(
                    text("SELECT COUNT(*) FROM schema_migration")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM control_framework")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM control_item")
                ).scalar_one(),
                connection.execute(
                    text("SELECT COUNT(*) FROM authorization_purpose")
                ).scalar_one(),
            )
        assert first == second == (POLICY_INTEGRITY_MIGRATION,)
        assert after == before
    finally:
        engine.dispose()


def test_postgresql_runtime_rejects_unknown_future_migration() -> None:
    """An older runtime refuses a real PostgreSQL schema carrying a future receipt."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES ('9999_future_schema', CURRENT_TIMESTAMP)"
                )
            )
        try:
            with pytest.raises(SchemaCompatibilityError, match="ahead"):
                create_session_factory(
                    _database_url(),
                    manage_schema=False,
                    postgres_settings=_settings(),
                )
        finally:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM schema_migration "
                        "WHERE migration_key = '9999_future_schema'"
                    )
                )
    finally:
        engine.dispose()


def test_postgresql_runtime_rejects_missing_required_migration() -> None:
    """A real PostgreSQL runtime refuses a schema missing its required receipt."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.begin() as connection:
            applied_at = connection.execute(
                text(
                    "DELETE FROM schema_migration "
                    "WHERE migration_key = :migration_key "
                    "RETURNING applied_at"
                ),
                {"migration_key": POLICY_INTEGRITY_MIGRATION},
            ).scalar_one()
        try:
            with pytest.raises(SchemaCompatibilityError, match="behind"):
                create_session_factory(
                    _database_url(),
                    manage_schema=False,
                    postgres_settings=_settings(),
                )
        finally:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO schema_migration (migration_key, applied_at) "
                        "VALUES (:migration_key, :applied_at)"
                    ),
                    {
                        "migration_key": POLICY_INTEGRITY_MIGRATION,
                        "applied_at": applied_at,
                    },
                )
    finally:
        engine.dispose()


def test_postgresql_stale_policy_writer_receives_conflict() -> None:
    """Real PostgreSQL optimistic allocation rejects a stale policy writer."""
    factory = create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )
    first = factory()
    stale = factory()
    try:
        decision = AuthorizationDecision(
            "postgresql-author",
            PurposeCode.POLICY_AUTHORING,
        )
        document = author_policy(
            first,
            decision,
            f"PostgreSQL concurrency {datetime.now(timezone.utc).isoformat()}",
            "The first edition establishes the optimistic revision token.",
            [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
        )
        first.commit()
        document_id = document.policy_document_id
        first_document = first.get(type(document), document_id)
        stale_document = stale.get(type(document), document_id)
        assert first_document is not None
        assert stale_document is not None
        assert first_document.current_version_number == 1
        assert stale_document.current_version_number == 1

        revise_policy(
            first,
            AuthorizationDecision(
                "postgresql-first-writer",
                PurposeCode.POLICY_AUTHORING,
            ),
            document_id,
            "The second edition advances the shared optimistic token.",
            [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
        )
        first.commit()

        with pytest.raises(HTTPException) as conflict:
            revise_policy(
                stale,
                AuthorizationDecision(
                    "postgresql-stale-writer",
                    PurposeCode.POLICY_AUTHORING,
                ),
                document_id,
                "This stale edition must reload before retrying.",
                [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
            )
        assert conflict.value.status_code == 409
        stale.rollback()
    finally:
        first.close()
        stale.close()
        factory.kw["bind"].dispose()


def test_postgresql_pool_exhaustion_fails_within_configured_bound() -> None:
    """A saturated pool raises a typed timeout instead of waiting indefinitely."""
    settings = _settings(
        pool_size=1,
        max_overflow=0,
        pool_timeout_seconds=1,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    try:
        with engine.connect():
            started = monotonic()
            with pytest.raises(SqlAlchemyTimeoutError):
                engine.connect()
            elapsed = monotonic() - started
        assert 0.8 <= elapsed < 3.0
    finally:
        engine.dispose()


def test_postgresql_statement_timeout_interrupts_long_query() -> None:
    """The configured statement deadline cancels long-running SQL promptly."""
    settings = _settings(
        statement_timeout_ms=150,
        lock_timeout_ms=50,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    try:
        with engine.connect() as connection:
            started = monotonic()
            with pytest.raises(DBAPIError, match="statement timeout"):
                connection.execute(text("SELECT pg_sleep(1)"))
            elapsed = monotonic() - started
        assert elapsed < 2.0
    finally:
        engine.dispose()


def test_postgresql_lock_timeout_interrupts_blocked_mutation() -> None:
    """Row-lock contention fails at the lock deadline before statement timeout."""
    settings = _settings(
        statement_timeout_ms=1_000,
        lock_timeout_ms=150,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS operational_lock_probe ("
                    "probe_id INTEGER PRIMARY KEY, probe_value INTEGER NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO operational_lock_probe (probe_id, probe_value) "
                    "VALUES (1, 0) ON CONFLICT (probe_id) DO UPDATE SET probe_value = 0"
                )
            )
        with engine.connect() as blocker, engine.connect() as contender:
            blocker.begin()
            blocker.execute(
                text(
                    "UPDATE operational_lock_probe SET probe_value = 1 "
                    "WHERE probe_id = 1"
                )
            )
            started = monotonic()
            with pytest.raises(DBAPIError, match="lock timeout"):
                contender.execute(
                    text(
                        "UPDATE operational_lock_probe SET probe_value = 2 "
                        "WHERE probe_id = 1"
                    )
                )
            elapsed = monotonic() - started
            blocker.rollback()
            contender.rollback()
        assert elapsed < 2.0
    finally:
        engine.dispose()


def test_postgresql_connection_loss_is_visible_and_pool_recovers() -> None:
    """A terminated backend fails the active operation and a later checkout recovers."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    victim = engine.connect()
    killer = engine.connect()
    try:
        backend_pid = victim.execute(text("SELECT pg_backend_pid()")) .scalar_one()
        terminated = killer.execute(
            text("SELECT pg_terminate_backend(:backend_pid)"),
            {"backend_pid": backend_pid},
        ).scalar_one()
        killer.commit()
        assert terminated is True
        with pytest.raises(DBAPIError):
            victim.execute(text("SELECT 1"))
    finally:
        victim.close()
        killer.close()
    try:
        with engine.connect() as recovered:
            assert recovered.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
