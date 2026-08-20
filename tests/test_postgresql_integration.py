"""Real PostgreSQL lifecycle, locking, timeout, and trigger acceptance tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from cwl_grc.authorization import PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import seed_control_catalog
from cwl_grc.database import (
    POSTGRESQL_MIGRATION_LOCK_KEY,
    PostgresEngineSettings,
    SchemaCompatibilityError,
    build_engine,
    create_session_factory,
    migrate_database,
)
from cwl_grc.migrations import POLICY_INTEGRITY_MIGRATION
from cwl_grc.models import AuditEvent


POSTGRESQL_URL = os.environ.get("CWL_GRC_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    POSTGRESQL_URL is None,
    reason="CWL_GRC_TEST_POSTGRES_URL selects the real PostgreSQL acceptance lane.",
)


def _database_url() -> str:
    """Return the explicit integration database URL or fail the selected lane."""
    assert POSTGRESQL_URL is not None
    return POSTGRESQL_URL


def _settings() -> PostgresEngineSettings:
    """Return the explicit loopback-only CI connection policy."""
    return PostgresEngineSettings(
        sslmode="disable",
        allow_insecure_loopback=True,
    )


@pytest.fixture(scope="module", autouse=True)
def clean_postgresql_schema() -> None:
    """Reset the isolated service database before the module acceptance sequence."""
    if POSTGRESQL_URL is None:
        return
    engine = build_engine(_database_url(), postgres_settings=_settings())
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def test_postgresql_clean_install_and_runtime_compatibility() -> None:
    """PostgreSQL 18 accepts explicit migration and later DDL-free runtime startup."""
    receipts = migrate_database(_database_url(), postgres_settings=_settings())
    assert receipts == (POLICY_INTEGRITY_MIGRATION,)

    factory = create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )
    try:
        with factory() as session:
            seed_control_catalog(session)
            seed_authorization_purposes(session)
            session.commit()
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


def test_postgresql_audit_trigger_matches_sqlite_integrity_contract() -> None:
    """The real PostgreSQL trigger rejects an audit-event mutation at SQL boundary."""
    factory = create_session_factory(
        _database_url(),
        manage_schema=False,
        postgres_settings=_settings(),
    )
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


def test_postgresql_runtime_restart_reuses_exact_schema() -> None:
    """A fresh process checks and reuses the migrated schema without creating DDL."""
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
