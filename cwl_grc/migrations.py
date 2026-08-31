"""Versioned schema upgrades and database-enforced immutability guards."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, inspect, text


POLICY_INTEGRITY_MIGRATION = "0001_policy_integrity"
TENANT_OWNERSHIP_MIGRATION = "0002_tenant_ownership"
AUDIT_ATTRIBUTION_MIGRATION = "0003_audit_attribution"
LOCAL_PREVIEW_TENANT = "local_preview"
LOCAL_PREVIEW_ISSUER = "local_preview"
LOCAL_PREVIEW_CLIENT = "local_preview"
LEGACY_UNATTRIBUTED_CORRELATION = "legacy_unattributed"
DECISION_ALLOW = "allow"


def apply_schema_migrations(engine: Engine) -> None:
    """Upgrade an existing first-slice store before installing integrity guards."""
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migration (
                    migration_key VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        _apply_named_migration(
            connection,
            POLICY_INTEGRITY_MIGRATION,
            _upgrade_policy_integrity,
        )
        _apply_named_migration(
            connection,
            TENANT_OWNERSHIP_MIGRATION,
            _upgrade_tenant_ownership,
        )
        _apply_named_migration(
            connection,
            AUDIT_ATTRIBUTION_MIGRATION,
            _upgrade_audit_attribution,
        )


def _apply_named_migration(
    connection: Any,
    migration_key: str,
    upgrade: Callable[[Any], None],
) -> None:
    """Apply one upgrade exactly once and record the receipt."""
    applied = connection.execute(
        text(
            "SELECT migration_key FROM schema_migration "
            "WHERE migration_key = :migration_key"
        ),
        {"migration_key": migration_key},
    ).scalar_one_or_none()
    if applied is not None:
        return
    upgrade(connection)
    connection.execute(
        text(
            "INSERT INTO schema_migration (migration_key, applied_at) "
            "VALUES (:migration_key, :applied_at)"
        ),
        {
            "migration_key": migration_key,
            "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
        },
    )


def _upgrade_policy_integrity(connection: Any) -> None:
    """Add policy counters and finalization flags to a pre-integrity store."""
    inspector = inspect(connection)
    additions = (
        (
            "policy_document",
            "current_version_number",
            "ALTER TABLE policy_document ADD COLUMN "
            "current_version_number INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "policy_version",
            "is_finalized",
            "ALTER TABLE policy_version ADD COLUMN "
            "is_finalized BOOLEAN NOT NULL DEFAULT TRUE",
        ),
    )
    for table_name, column_name, statement in additions:
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if column_name not in columns:
            connection.execute(text(statement))
            inspector = inspect(connection)

    connection.execute(
        text(
            """
            UPDATE policy_document
            SET current_version_number = COALESCE(
                (
                    SELECT MAX(policy_version.version_number)
                    FROM policy_version
                    WHERE policy_version.policy_document_id =
                          policy_document.policy_document_id
                ),
                0
            )
            WHERE current_version_number = 0
            """
        )
    )
    connection.execute(
        text("UPDATE policy_version SET is_finalized = TRUE WHERE is_finalized IS NULL")
    )


def _upgrade_tenant_ownership(connection: Any) -> None:
    """Stamp owned records with a tenant identifier for Keyverse isolation."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    additions = (
        (
            "policy_document",
            "ALTER TABLE policy_document ADD COLUMN "
            f"tenant_identifier VARCHAR(128) NOT NULL DEFAULT '{LOCAL_PREVIEW_TENANT}'",
            "CREATE INDEX IF NOT EXISTS policy_document_tenant_actor "
            "ON policy_document (tenant_identifier, created_by_actor)",
        ),
        (
            "evidence_record",
            "ALTER TABLE evidence_record ADD COLUMN "
            f"tenant_identifier VARCHAR(128) NOT NULL DEFAULT '{LOCAL_PREVIEW_TENANT}'",
            "CREATE INDEX IF NOT EXISTS evidence_record_tenant_actor "
            "ON evidence_record (tenant_identifier, collector_actor)",
        ),
        (
            "audit_event",
            "ALTER TABLE audit_event ADD COLUMN "
            f"tenant_identifier VARCHAR(128) NOT NULL DEFAULT '{LOCAL_PREVIEW_TENANT}'",
            "",
        ),
    )
    for table_name, alter_sql, index_sql in additions:
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_identifier" not in columns:
            connection.execute(text(alter_sql))
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
        if index_sql:
            connection.execute(text(index_sql))


def _upgrade_audit_attribution(connection: Any) -> None:
    """Add issuer, client, correlation, and decision fields to existing audit rows."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "audit_event" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("audit_event")}
    additions = (
        (
            "issuer_identifier",
            "ALTER TABLE audit_event ADD COLUMN "
            f"issuer_identifier VARCHAR(1024) NOT NULL DEFAULT '{LOCAL_PREVIEW_ISSUER}'",
        ),
        (
            "client_identifier",
            "ALTER TABLE audit_event ADD COLUMN "
            f"client_identifier VARCHAR(128) NOT NULL DEFAULT '{LOCAL_PREVIEW_CLIENT}'",
        ),
        (
            "correlation_reference",
            "ALTER TABLE audit_event ADD COLUMN "
            "correlation_reference VARCHAR(128) NOT NULL "
            f"DEFAULT '{LEGACY_UNATTRIBUTED_CORRELATION}'",
        ),
        (
            "decision_outcome",
            "ALTER TABLE audit_event ADD COLUMN "
            f"decision_outcome VARCHAR(32) NOT NULL DEFAULT '{DECISION_ALLOW}'",
        ),
    )
    for column_name, alter_sql in additions:
        if column_name not in columns:
            connection.execute(text(alter_sql))
            inspector = inspect(connection)
            columns = {column["name"] for column in inspector.get_columns("audit_event")}
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS audit_event_tenant_correlation "
            "ON audit_event (tenant_identifier, correlation_reference)"
        )
    )


def install_integrity_guards(engine: Engine) -> None:
    """Install idempotent database triggers for append-only and finalized rows."""
    statements = integrity_guard_statements(engine.dialect.name)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def integrity_guard_statements(dialect_name: str) -> Sequence[str]:
    """Return complete trigger DDL for SQLite or PostgreSQL."""
    if dialect_name == "sqlite":
        return _sqlite_integrity_guard_statements()
    if dialect_name == "postgresql":
        return _postgresql_integrity_guard_statements()
    raise ValueError(f"Unsupported GRC database dialect: {dialect_name}")


def _sqlite_integrity_guard_statements() -> tuple[str, ...]:
    """Return SQLite triggers that make audit and finalized policy rows immutable."""
    return (
        """
        CREATE TRIGGER IF NOT EXISTS audit_event_block_update
        BEFORE UPDATE ON audit_event
        BEGIN
            SELECT RAISE(ABORT, 'audit_event is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_event_block_delete
        BEFORE DELETE ON audit_event
        BEGIN
            SELECT RAISE(ABORT, 'audit_event is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_version_require_open_insert
        BEFORE INSERT ON policy_version
        WHEN NEW.is_finalized != 0
        BEGIN
            SELECT RAISE(ABORT, 'new policy_version must start unfinalized');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_version_block_delete
        BEFORE DELETE ON policy_version
        BEGIN
            SELECT RAISE(ABORT, 'finalized policy_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_version_finalize_only
        BEFORE UPDATE ON policy_version
        WHEN NOT (
            OLD.is_finalized = 0
            AND NEW.is_finalized = 1
            AND OLD.policy_version_id = NEW.policy_version_id
            AND OLD.policy_document_id = NEW.policy_document_id
            AND OLD.version_number = NEW.version_number
            AND OLD.policy_body = NEW.policy_body
            AND OLD.authored_by_actor = NEW.authored_by_actor
            AND OLD.authored_at = NEW.authored_at
        )
        BEGIN
            SELECT RAISE(ABORT, 'finalized policy_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_control_mapping_block_update
        BEFORE UPDATE ON policy_control_mapping
        BEGIN
            SELECT RAISE(ABORT, 'policy_control_mapping is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_control_mapping_block_delete
        BEFORE DELETE ON policy_control_mapping
        BEGIN
            SELECT RAISE(ABORT, 'policy_control_mapping is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS policy_control_mapping_require_open_version
        BEFORE INSERT ON policy_control_mapping
        WHEN COALESCE(
            (
                SELECT is_finalized
                FROM policy_version
                WHERE policy_version_id = NEW.policy_version_id
            ),
            1
        ) != 0
        BEGIN
            SELECT RAISE(ABORT, 'cannot add mapping to finalized policy_version');
        END
        """,
    )


def _postgresql_integrity_guard_statements() -> tuple[str, ...]:
    """Return PostgreSQL functions and triggers with the same integrity contract."""
    return (
        """
        CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only';
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS audit_event_immutable ON audit_event",
        """
        CREATE TRIGGER audit_event_immutable
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()
        """,
        """
        CREATE OR REPLACE FUNCTION prevent_policy_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.is_finalized THEN
                    RAISE EXCEPTION 'new policy_version must start unfinalized';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'finalized policy_version is immutable';
            END IF;
            IF OLD.is_finalized
               OR NOT NEW.is_finalized
               OR (to_jsonb(OLD) - 'is_finalized') IS DISTINCT FROM
                  (to_jsonb(NEW) - 'is_finalized') THEN
                RAISE EXCEPTION 'finalized policy_version is immutable';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS policy_version_immutable ON policy_version",
        """
        CREATE TRIGGER policy_version_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON policy_version
        FOR EACH ROW EXECUTE FUNCTION prevent_policy_version_mutation()
        """,
        """
        CREATE OR REPLACE FUNCTION prevent_policy_mapping_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            parent_finalized BOOLEAN;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                SELECT is_finalized INTO parent_finalized
                FROM policy_version
                WHERE policy_version_id = NEW.policy_version_id;
                IF COALESCE(parent_finalized, TRUE) THEN
                    RAISE EXCEPTION 'cannot add mapping to finalized policy_version';
                END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'policy_control_mapping is immutable';
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS policy_control_mapping_immutable ON policy_control_mapping",
        """
        CREATE TRIGGER policy_control_mapping_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON policy_control_mapping
        FOR EACH ROW EXECUTE FUNCTION prevent_policy_mapping_mutation()
        """,
    )
