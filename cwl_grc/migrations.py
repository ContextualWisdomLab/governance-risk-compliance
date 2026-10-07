"""Versioned schema upgrades and database-enforced immutability guards."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Connection, Engine, inspect, text

from cwl_grc.models import Base


POLICY_INTEGRITY_MIGRATION = "0001_policy_integrity"
AUDIT_MANAGEMENT_MIGRATION = "0002_audit_management"

AUDIT_MANAGEMENT_TABLES = (
    "audit_program",
    "audit_engagement",
    "engagement_criterion",
    "engagement_team_member",
    "independence_declaration",
    "audit_procedure",
    "audit_sample_item",
    "audit_evidence_link",
    "audit_finding",
    "audit_finding_revision",
    "remediation_action",
    "finding_retest",
    "finding_closure",
)

IMMUTABLE_AUDIT_TABLES = (
    "audit_finding_revision",
    "independence_declaration",
    "finding_retest",
    "finding_closure",
)


def apply_schema_migrations(engine: Engine) -> None:
    """Upgrade an existing store, recording one idempotent receipt per migration."""
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
        if not _migration_applied(connection, POLICY_INTEGRITY_MIGRATION):
            _apply_policy_integrity(connection)
            _record_migration(connection, POLICY_INTEGRITY_MIGRATION)
        if not _migration_applied(connection, AUDIT_MANAGEMENT_MIGRATION):
            _apply_audit_management(connection)
            _record_migration(connection, AUDIT_MANAGEMENT_MIGRATION)


def _migration_applied(connection: Connection, migration_key: str) -> bool:
    """Return whether a migration receipt already exists."""
    applied = connection.execute(
        text(
            "SELECT migration_key FROM schema_migration "
            "WHERE migration_key = :migration_key"
        ),
        {"migration_key": migration_key},
    ).scalar_one_or_none()
    return applied is not None


def _record_migration(connection: Connection, migration_key: str) -> None:
    """Insert one migration receipt."""
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


def _apply_audit_management(connection: Connection) -> None:
    """Create any missing audit-management tables without touching existing rows."""
    Base.metadata.create_all(
        connection,
        tables=[Base.metadata.tables[name] for name in AUDIT_MANAGEMENT_TABLES],
        checkfirst=True,
    )


def _apply_policy_integrity(connection: Connection) -> None:
    """Add policy revision counters and finalization state to a first-slice store."""
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


def install_integrity_guards(engine: Engine) -> None:
    """Install idempotent database triggers for append-only and finalized rows."""
    statements = integrity_guard_statements(engine.dialect.name)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def integrity_guard_statements(dialect_name: str) -> Sequence[str]:
    """Return complete trigger DDL for SQLite or PostgreSQL."""
    if dialect_name == "sqlite":
        return _sqlite_integrity_guard_statements() + _sqlite_audit_record_guards()
    if dialect_name == "postgresql":
        return _postgresql_integrity_guard_statements() + _postgresql_audit_record_guards()
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


def _sqlite_audit_record_guards() -> tuple[str, ...]:
    """Return SQLite triggers that make audit-management decision records immutable."""
    statements: list[str] = []
    for table in IMMUTABLE_AUDIT_TABLES:
        for operation in ("update", "delete"):
            statements.append(
                f"""
        CREATE TRIGGER IF NOT EXISTS {table}_block_{operation}
        BEFORE {operation.upper()} ON {table}
        BEGIN
            SELECT RAISE(ABORT, '{table} is immutable');
        END
        """
            )
    return tuple(statements)


def _postgresql_audit_record_guards() -> tuple[str, ...]:
    """Return one PostgreSQL function and per-table triggers for immutable audit records."""
    statements: list[str] = [
        """
        CREATE OR REPLACE FUNCTION prevent_audit_record_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$
        """
    ]
    for table in IMMUTABLE_AUDIT_TABLES:
        statements.append(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        statements.append(
            f"""
        CREATE TRIGGER {table}_immutable
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_record_mutation()
        """
        )
    return tuple(statements)
