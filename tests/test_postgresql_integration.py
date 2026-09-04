"""Real PostgreSQL lifecycle, locking, timeout, and trigger acceptance tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, TimeoutError

from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog import FrameworkCode
from cwl_grc.database import (
    CATALOG_SEED_ROWS,
    EXPECTED_PURPOSE_ROWS,
    POSTGRESQL_MIGRATION_LOCK_KEY,
    PostgresEngineSettings,
    SchemaCompatibilityError,
    build_engine,
    create_session_factory,
    migrate_database,
)
from cwl_grc.migrations import POLICY_INTEGRITY_MIGRATION
from cwl_grc.models import (
    AuditEvent,
    PolicyControlMapping,
    PolicyDocument,
    PolicyVersion,
)
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


def _settings(**overrides: int | str | bool) -> PostgresEngineSettings:
    """Return the explicit loopback-only CI connection policy with bounded overrides."""
    values: dict[str, int | str | bool] = {
        "sslmode": "disable",
        "allow_insecure_loopback": True,
    }
    values.update(overrides)
    return PostgresEngineSettings(**values)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def clean_postgresql_schema() -> None:
    """Reset the isolated service database before each acceptance contract."""
    if POSTGRESQL_URL is None:
        return
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def _runtime_factory():  # noqa: ANN202
    """Migrate once and return one DDL-free PostgreSQL runtime factory."""
    receipts = migrate_database(_database_url(), postgres_settings=_settings())
    assert receipts == (POLICY_INTEGRITY_MIGRATION,)
    return create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )


def _author_policy(factory) -> str:  # noqa: ANN001
    """Author one finalized PostgreSQL policy and return its stable identifier."""
    with factory() as session:
        document = author_policy(
            session,
            AuthorizationDecision(
                "postgresql-officer",
                PurposeCode.POLICY_AUTHORING,
            ),
            "PostgreSQL integrity policy",
            "The current edition is protected by the database boundary.",
            [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
        )
        document_id = document.policy_document_id
        session.commit()
    return document_id


def test_postgresql_clean_install_and_runtime_compatibility() -> None:
    """PostgreSQL 18 accepts explicit migration and later DDL-free runtime startup."""
    factory = _runtime_factory()
    try:
        with factory() as session:
            server_version = session.execute(text("SHOW server_version")).scalar_one()
            statement_timeout = session.execute(
                text("SHOW statement_timeout")
            ).scalar_one()
            lock_timeout = session.execute(text("SHOW lock_timeout")).scalar_one()
            idle_timeout = session.execute(
                text("SHOW idle_in_transaction_session_timeout")
            ).scalar_one()
        assert server_version.startswith("18.4")
        assert statement_timeout == "30s"
        assert lock_timeout == "5s"
        assert idle_timeout == "1min"
    finally:
        factory.kw["bind"].dispose()


def test_postgresql_migration_rerun_is_idempotent() -> None:
    """A completed migration can be rerun without duplicate receipts or vocabulary."""
    first = migrate_database(_database_url(), postgres_settings=_settings())
    second = migrate_database(_database_url(), postgres_settings=_settings())
    assert first == second == (POLICY_INTEGRITY_MIGRATION,)
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.connect() as connection:
            migration_count = connection.execute(
                text("SELECT COUNT(*) FROM schema_migration")
            ).scalar_one()
            control_count = connection.execute(
                text("SELECT COUNT(*) FROM control_item")
            ).scalar_one()
            purpose_count = connection.execute(
                text("SELECT COUNT(*) FROM authorization_purpose")
            ).scalar_one()
        assert migration_count == 1
        assert control_count == len(CATALOG_SEED_ROWS)
        assert purpose_count == len(EXPECTED_PURPOSE_ROWS)
    finally:
        engine.dispose()


def test_postgresql_audit_trigger_matches_sqlite_integrity_contract() -> None:
    """The real PostgreSQL trigger rejects an audit-event mutation at SQL boundary."""
    factory = _runtime_factory()
    try:
        with factory() as session:
            event = AuditEvent(
                audit_event_id=uuid4().hex,
                actor_identifier="postgresql-officer",
                purpose_code=PurposeCode.POLICY_AUTHORING.value,
                action_name="postgresql_acceptance",
                resource_kind="schema_lifecycle",
                resource_identifier="postgresql-18.4",
                recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(event)
            session.commit()
            with pytest.raises(DBAPIError, match="append-only"):
                session.execute(
                    update(AuditEvent)
                    .where(AuditEvent.audit_event_id == event.audit_event_id)
                    .values(action_name="tampered")
                )
                session.commit()
            session.rollback()
    finally:
        factory.kw["bind"].dispose()


def test_postgresql_finalized_policy_and_mapping_are_immutable() -> None:
    """PostgreSQL protects finalized policy text and mappings like SQLite."""
    factory = _runtime_factory()
    try:
        document_id = _author_policy(factory)
        with factory() as session:
            version = (
                session.query(PolicyVersion)
                .filter_by(policy_document_id=document_id)
                .one()
            )
            mapping = (
                session.query(PolicyControlMapping)
                .filter_by(policy_version_id=version.policy_version_id)
                .one()
            )
            assert version.is_finalized is True
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(
                    update(PolicyVersion)
                    .where(PolicyVersion.policy_version_id == version.policy_version_id)
                    .values(policy_body="Tampered policy text.")
                )
                session.commit()
            session.rollback()
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(
                    delete(PolicyControlMapping).where(
                        PolicyControlMapping.mapping_id == mapping.mapping_id
                    )
                )
                session.commit()
            session.rollback()
    finally:
        factory.kw["bind"].dispose()


def test_postgresql_stale_policy_writer_receives_conflict() -> None:
    """Two PostgreSQL writers cannot publish from the same stale revision token."""
    factory = _runtime_factory()
    document_id = _author_policy(factory)
    first = factory()
    stale = factory()
    try:
        first_document = first.get(PolicyDocument, document_id)
        stale_document = stale.get(PolicyDocument, document_id)
        assert first_document is not None
        assert stale_document is not None
        assert first_document.current_version_number == 1
        assert stale_document.current_version_number == 1
        revise_policy(
            first,
            AuthorizationDecision("postgresql-first", PurposeCode.POLICY_AUTHORING),
            document_id,
            "The second PostgreSQL edition wins the optimistic allocation.",
            [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
        )
        first.commit()
        with pytest.raises(HTTPException) as conflict:
            revise_policy(
                stale,
                AuthorizationDecision("postgresql-stale", PurposeCode.POLICY_AUTHORING),
                document_id,
                "The stale PostgreSQL writer must reload before publishing.",
                [ControlRef(FrameworkCode.SOC2_TSC_2017, "CC1.1")],
            )
        assert conflict.value.status_code == 409
    finally:
        first.close()
        stale.close()
        factory.kw["bind"].dispose()


def test_postgresql_concurrent_migration_writer_fails_before_ddl() -> None:
    """A second migration owner fails immediately while the advisory key is held."""
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.connect() as blocker:
            blocker.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": POSTGRESQL_MIGRATION_LOCK_KEY},
            )
            try:
                with pytest.raises(SchemaCompatibilityError, match="advisory lock"):
                    migrate_database(_database_url(), postgres_settings=_settings())
            finally:
                released = blocker.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": POSTGRESQL_MIGRATION_LOCK_KEY},
                ).scalar_one()
                assert released is True
    finally:
        engine.dispose()


def test_postgresql_statement_timeout_is_bounded() -> None:
    """A long statement is cancelled by the configured server-side timeout."""
    settings = _settings(
        statement_timeout_ms=300,
        lock_timeout_ms=100,
        idle_transaction_timeout_ms=2_000,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    started = monotonic()
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="statement timeout"):
                connection.execute(text("SELECT pg_sleep(5)"))
    finally:
        elapsed = monotonic() - started
        engine.dispose()
    assert 0.1 <= elapsed < 2.0


def test_postgresql_lock_timeout_is_bounded() -> None:
    """A blocked write fails on lock timeout before the statement timeout."""
    migrate_database(_database_url(), postgres_settings=_settings())
    settings = _settings(
        statement_timeout_ms=2_000,
        lock_timeout_ms=300,
        idle_transaction_timeout_ms=5_000,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    blocker = engine.connect()
    waiter = engine.connect()
    statement = text(
        "UPDATE schema_migration SET applied_at = applied_at "
        "WHERE migration_key = :migration_key"
    )
    try:
        blocker.execute(
            statement,
            {"migration_key": POLICY_INTEGRITY_MIGRATION},
        )
        started = monotonic()
        with pytest.raises(DBAPIError, match="lock timeout"):
            waiter.execute(
                statement,
                {"migration_key": POLICY_INTEGRITY_MIGRATION},
            )
        elapsed = monotonic() - started
        assert 0.1 <= elapsed < 2.0
    finally:
        waiter.rollback()
        blocker.rollback()
        waiter.close()
        blocker.close()
        engine.dispose()


def test_postgresql_pool_exhaustion_is_bounded() -> None:
    """A saturated runtime pool fails within the configured acquisition timeout."""
    settings = _settings(
        pool_size=1,
        max_overflow=0,
        pool_timeout_seconds=1,
    )
    engine = build_engine(_database_url(), postgres_settings=settings)
    held = engine.connect()
    try:
        started = monotonic()
        with pytest.raises(TimeoutError, match="QueuePool limit"):
            engine.connect()
        elapsed = monotonic() - started
        assert 0.5 <= elapsed < 3.0
    finally:
        held.close()
        engine.dispose()


def test_postgresql_pre_ping_replaces_a_terminated_pooled_connection() -> None:
    """A server-terminated idle connection is detected before reuse."""
    migrate_database(_database_url(), postgres_settings=_settings())
    engine = build_engine(_database_url(), postgres_settings=_settings())
    killer = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.connect() as connection:
            terminated_pid = connection.execute(
                text("SELECT pg_backend_pid()")
            ).scalar_one()
        with killer.connect() as connection:
            terminated = connection.execute(
                text("SELECT pg_terminate_backend(:backend_pid)"),
                {"backend_pid": terminated_pid},
            ).scalar_one()
        assert terminated is True
        with engine.connect() as connection:
            replacement_pid = connection.execute(
                text("SELECT pg_backend_pid()")
            ).scalar_one()
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert replacement_pid != terminated_pid
    finally:
        killer.dispose()
        engine.dispose()


def test_postgresql_runtime_rejects_future_schema_receipt() -> None:
    """An older runtime refuses a PostgreSQL schema carrying a future migration."""
    migrate_database(_database_url(), postgres_settings=_settings())
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES ('9999_future_schema', CURRENT_TIMESTAMP)"
                )
            )
        with pytest.raises(SchemaCompatibilityError, match="ahead"):
            create_session_factory(
                _database_url(),
                manage_schema=False,
                postgres_settings=_settings(),
            )
    finally:
        engine.dispose()


def test_postgresql_runtime_restart_reuses_exact_schema() -> None:
    """A fresh process checks and reuses the migrated schema without creating DDL."""
    migrate_database(_database_url(), postgres_settings=_settings())
    first = create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )
    first.kw["bind"].dispose()
    second = create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )
    try:
        with second() as session:
            count = session.execute(
                text("SELECT COUNT(*) FROM schema_migration")
            ).scalar_one()
        assert count == 1
    finally:
        second.kw["bind"].dispose()


def test_postgresql_workflow_uses_pinned_current_major_image() -> None:
    """The acceptance workflow pins the reviewed PostgreSQL 18.4 image index."""
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/postgresql-integration.yml"
    ).read_text(encoding="utf-8")
    assert (
        "postgres:18.4-bookworm@sha256:"
        "882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382"
    ) in workflow
