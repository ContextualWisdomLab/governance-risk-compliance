"""Versioned schema upgrades and database-enforced immutability guards."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Engine, inspect, text


POLICY_INTEGRITY_MIGRATION = "0001_policy_integrity"
API_IDEMPOTENCY_MIGRATION = "0005_api_idempotency"


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
        policy_integrity_applied = connection.execute(
            text(
                "SELECT migration_key FROM schema_migration "
                "WHERE migration_key = :migration_key"
            ),
            {"migration_key": POLICY_INTEGRITY_MIGRATION},
        ).scalar_one_or_none()
        if policy_integrity_applied is None:
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
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES (:migration_key, :applied_at)"
                ),
                {
                    "migration_key": POLICY_INTEGRITY_MIGRATION,
                    "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
            )

        api_idempotency_applied = connection.execute(
            text(
                "SELECT migration_key FROM schema_migration "
                "WHERE migration_key = :migration_key"
            ),
            {"migration_key": API_IDEMPOTENCY_MIGRATION},
        ).scalar_one_or_none()
        if api_idempotency_applied is None:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS idempotency_record (
                        idempotency_record_id VARCHAR(64) PRIMARY KEY,
                        actor_identifier VARCHAR(128) NOT NULL,
                        operation_name VARCHAR(64) NOT NULL,
                        idempotency_key VARCHAR(255) NOT NULL,
                        request_digest VARCHAR(64) NOT NULL,
                        response_status INTEGER NOT NULL,
                        response_payload TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        CONSTRAINT idempotency_record_scope
                            UNIQUE (actor_identifier, operation_name, idempotency_key)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES (:migration_key, :applied_at)"
                ),
                {
                    "migration_key": API_IDEMPOTENCY_MIGRATION,
                    "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
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
