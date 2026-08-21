"""Versioned schema upgrades and database-enforced immutability guards."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import Connection, Engine, Index, MetaData, Table, insert, inspect, select, text


POLICY_INTEGRITY_MIGRATION = "0001_policy_integrity"
TENANT_ISOLATION_MIGRATION = "0002_tenant_isolation"
EVIDENCE_ENCRYPTION_MIGRATION = "0003_evidence_encryption"
EVIDENCE_RETENTION_MIGRATION = "0004_evidence_retention"
INTERNAL_CONTROL_MODEL_MIGRATION = "0005_internal_control_model"
LOCAL_DEVELOPMENT_TENANT = "local_development"
TENANT_OWNED_TABLES = (
    "policy_document",
    "policy_version",
    "policy_control_mapping",
    "evidence_record",
    "control_evidence_binding",
    "audit_event",
    "control_objective",
    "internal_control_definition",
    "control_definition_version",
    "control_implementation",
    "control_owner_assignment",
    "control_requirement_mapping",
    "control_test_plan",
    "control_test_execution",
    "control_test_result",
    "control_exception",
    "control_deficiency",
    "evidence_usage",
)
TENANT_COLUMN_ADDITIONS = (
    (
        "policy_document",
        "ALTER TABLE policy_document ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
    (
        "policy_version",
        "ALTER TABLE policy_version ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
    (
        "policy_control_mapping",
        "ALTER TABLE policy_control_mapping ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
    (
        "evidence_record",
        "ALTER TABLE evidence_record ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
    (
        "control_evidence_binding",
        "ALTER TABLE control_evidence_binding ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
    (
        "audit_event",
        "ALTER TABLE audit_event ADD COLUMN tenant_id VARCHAR(128) "
        "NOT NULL DEFAULT 'local_development'",
    ),
)


def apply_schema_migrations(engine: Engine) -> None:
    """Apply every missing schema upgrade in order and retain migration receipts."""
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
            _apply_policy_integrity_migration(connection)
            _record_migration(connection, POLICY_INTEGRITY_MIGRATION)
        if not _migration_applied(connection, TENANT_ISOLATION_MIGRATION):
            _apply_tenant_isolation_migration(connection)
            _record_migration(connection, TENANT_ISOLATION_MIGRATION)
        if not _migration_applied(connection, EVIDENCE_ENCRYPTION_MIGRATION):
            _apply_evidence_encryption_migration(connection)
            _record_migration(connection, EVIDENCE_ENCRYPTION_MIGRATION)
        if not _migration_applied(connection, EVIDENCE_RETENTION_MIGRATION):
            _apply_evidence_retention_migration(connection)
            _record_migration(connection, EVIDENCE_RETENTION_MIGRATION)
        if not _migration_applied(connection, INTERNAL_CONTROL_MODEL_MIGRATION):
            _apply_internal_control_model_migration(connection)
            _record_migration(connection, INTERNAL_CONTROL_MODEL_MIGRATION)


def _migration_applied(connection: Connection, migration_key: str) -> bool:
    """Return whether one exact migration receipt already exists."""
    return (
        connection.execute(
            text(
                "SELECT migration_key FROM schema_migration "
                "WHERE migration_key = :migration_key"
            ),
            {"migration_key": migration_key},
        ).scalar_one_or_none()
        is not None
    )


def _record_migration(connection: Connection, migration_key: str) -> None:
    """Record one completed schema migration using an explicit UTC timestamp."""
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


def _apply_policy_integrity_migration(connection: Connection) -> None:
    """Upgrade legacy policy tables with revision and finalization state."""
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


def _apply_tenant_isolation_migration(connection: Connection) -> None:
    """Backfill tenant keys onto existing tenant-owned rows without inventing identities."""
    inspector = inspect(connection)
    for table_name, statement in TENANT_COLUMN_ADDITIONS:
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" in columns:
            continue
        connection.execute(text(statement))
        inspector = inspect(connection)


def _apply_evidence_encryption_migration(connection: Connection) -> None:
    """Add explicit legacy metadata before new evidence uses versioned envelopes."""
    inspector = inspect(connection)
    if not inspector.has_table("evidence_record"):
        return
    additions = (
        (
            "encryption_key_id",
            "ALTER TABLE evidence_record ADD COLUMN encryption_key_id VARCHAR(128) "
            "NOT NULL DEFAULT 'legacy-v1'",
        ),
        (
            "encryption_algorithm_version",
            "ALTER TABLE evidence_record ADD COLUMN encryption_algorithm_version VARCHAR(64) "
            "NOT NULL DEFAULT 'fernet-v1-legacy'",
        ),
        (
            "encryption_context_digest",
            "ALTER TABLE evidence_record ADD COLUMN encryption_context_digest VARCHAR(64) "
            "NOT NULL DEFAULT ''",
        ),
        (
            "source_content_digest",
            "ALTER TABLE evidence_record ADD COLUMN source_content_digest VARCHAR(64) "
            "NOT NULL DEFAULT ''",
        ),
        (
            "integrity_digest",
            "ALTER TABLE evidence_record ADD COLUMN integrity_digest VARCHAR(64) "
            "NOT NULL DEFAULT ''",
        ),
    )
    for column_name, statement in additions:
        columns = {column["name"] for column in inspector.get_columns("evidence_record")}
        if column_name not in columns:
            connection.execute(text(statement))
            inspector = inspect(connection)


def _apply_evidence_retention_migration(connection: Connection) -> None:
    """Add retention metadata while preserving legacy evidence timestamps."""
    inspector = inspect(connection)
    if not inspector.has_table("evidence_record"):
        return
    additions = (
        (
            "retention_class",
            "ALTER TABLE evidence_record ADD COLUMN retention_class VARCHAR(64) "
            "NOT NULL DEFAULT 'standard'",
        ),
        (
            "retention_started_at",
            "ALTER TABLE evidence_record ADD COLUMN retention_started_at TIMESTAMP "
            "NOT NULL DEFAULT '1970-01-01 00:00:00'",
        ),
        (
            "disposition_due_at",
            "ALTER TABLE evidence_record ADD COLUMN disposition_due_at TIMESTAMP",
        ),
        (
            "legal_hold_active",
            "ALTER TABLE evidence_record ADD COLUMN legal_hold_active BOOLEAN "
            "NOT NULL DEFAULT FALSE",
        ),
        (
            "legal_hold_reason",
            "ALTER TABLE evidence_record ADD COLUMN legal_hold_reason TEXT",
        ),
        (
            "legal_hold_authority",
            "ALTER TABLE evidence_record ADD COLUMN legal_hold_authority VARCHAR(255)",
        ),
        (
            "disposition_outcome",
            "ALTER TABLE evidence_record ADD COLUMN disposition_outcome VARCHAR(64)",
        ),
    )
    for column_name, statement in additions:
        columns = {column["name"] for column in inspect(connection).get_columns("evidence_record")}
        if column_name not in columns:
            connection.execute(text(statement))
    connection.execute(
        text(
            "UPDATE evidence_record SET retention_started_at = collected_at "
            "WHERE retention_started_at = '1970-01-01 00:00:00'"
        )
    )


def _apply_internal_control_model_migration(connection: Connection) -> None:
    """Create the internal-control tables and classify legacy bindings as unassessed."""
    from cwl_grc.models import Base

    inspector = inspect(connection)
    for table_name, index_name, column_names in (
        (
            "evidence_record",
            "evidence_record_tenant_identity_compat",
            ("tenant_id", "evidence_record_id"),
        ),
        (
            "control_evidence_binding",
            "control_evidence_binding_tenant_identity_compat",
            ("tenant_id", "binding_id"),
        ),
    ):
        if inspector.has_table(table_name):
            table = Table(table_name, MetaData(), autoload_with=connection)
            Index(
                index_name,
                *(table.c[column_name] for column_name in column_names),
                unique=True,
            ).create(connection, checkfirst=True)
    Base.metadata.create_all(connection)
    binding_table = Base.metadata.tables["control_evidence_binding"]
    usage_table = Base.metadata.tables["evidence_usage"]
    for binding in connection.execute(select(binding_table)).mappings():
        if connection.execute(
            select(usage_table.c.legacy_binding_id).where(
                usage_table.c.legacy_binding_id == binding["binding_id"]
            )
        ).first() is not None:
            continue
        usage_id = f"legacy_{sha256(binding['binding_id'].encode('utf-8')).hexdigest()[:57]}"
        connection.execute(
            insert(usage_table).values(
                evidence_usage_id=usage_id,
                tenant_id=binding["tenant_id"],
                evidence_record_id=binding["evidence_record_id"],
                legacy_binding_id=binding["binding_id"],
                purpose_code=binding["purpose_code"],
                usage_status="unassessed",
                usage_note="Legacy direct evidence binding; effectiveness not assessed.",
                used_by_actor=binding["bound_by_actor"],
                used_at=binding["bound_at"],
            )
        )


def install_integrity_guards(engine: Engine) -> None:
    """Install idempotent database triggers for immutable and tenant-bound rows."""
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
    """Return SQLite guards for immutable history and tenant-parent integrity."""
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
        CREATE TRIGGER IF NOT EXISTS policy_version_require_tenant_document
        BEFORE INSERT ON policy_version
        WHEN NOT EXISTS (
            SELECT 1
            FROM policy_document
            WHERE policy_document_id = NEW.policy_document_id
              AND tenant_id = NEW.tenant_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'policy_version tenant parent mismatch');
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
            AND OLD.tenant_id = NEW.tenant_id
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
                  AND tenant_id = NEW.tenant_id
            ),
            1
        ) != 0
        BEGIN
            SELECT RAISE(ABORT, 'cannot add mapping to finalized policy_version');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_binding_require_tenant_evidence_insert
        BEFORE INSERT ON control_evidence_binding
        WHEN NOT EXISTS (
            SELECT 1
            FROM evidence_record
            WHERE evidence_record_id = NEW.evidence_record_id
              AND tenant_id = NEW.tenant_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'control binding tenant parent mismatch');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_binding_require_tenant_evidence_update
        BEFORE UPDATE OF tenant_id, evidence_record_id ON control_evidence_binding
        WHEN NOT EXISTS (
            SELECT 1
            FROM evidence_record
            WHERE evidence_record_id = NEW.evidence_record_id
              AND tenant_id = NEW.tenant_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'control binding tenant parent mismatch');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_definition_version_block_update
        BEFORE UPDATE ON control_definition_version
        BEGIN
            SELECT RAISE(ABORT, 'control_definition_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_definition_version_block_delete
        BEFORE DELETE ON control_definition_version
        BEGIN
            SELECT RAISE(ABORT, 'control_definition_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_requirement_mapping_block_update
        BEFORE UPDATE ON control_requirement_mapping
        BEGIN
            SELECT RAISE(ABORT, 'control_requirement_mapping is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_requirement_mapping_block_delete
        BEFORE DELETE ON control_requirement_mapping
        BEGIN
            SELECT RAISE(ABORT, 'control_requirement_mapping is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_test_execution_block_update
        BEFORE UPDATE ON control_test_execution
        BEGIN
            SELECT RAISE(ABORT, 'control_test_execution is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_test_execution_block_delete
        BEFORE DELETE ON control_test_execution
        BEGIN
            SELECT RAISE(ABORT, 'control_test_execution is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_test_result_block_update
        BEFORE UPDATE ON control_test_result
        BEGIN
            SELECT RAISE(ABORT, 'control_test_result is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS control_test_result_block_delete
        BEFORE DELETE ON control_test_result
        BEGIN
            SELECT RAISE(ABORT, 'control_test_result is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS evidence_usage_block_update
        BEFORE UPDATE ON evidence_usage
        BEGIN
            SELECT RAISE(ABORT, 'evidence_usage is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS evidence_usage_block_delete
        BEFORE DELETE ON evidence_usage
        BEGIN
            SELECT RAISE(ABORT, 'evidence_usage is immutable');
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
                IF NOT EXISTS (
                    SELECT 1
                    FROM policy_document
                    WHERE policy_document_id = NEW.policy_document_id
                      AND tenant_id = NEW.tenant_id
                ) THEN
                    RAISE EXCEPTION 'policy_version tenant parent mismatch';
                END IF;
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
                WHERE policy_version_id = NEW.policy_version_id
                  AND tenant_id = NEW.tenant_id;
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
        """
        CREATE OR REPLACE FUNCTION enforce_control_binding_tenant_parent()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM evidence_record
                WHERE evidence_record_id = NEW.evidence_record_id
                  AND tenant_id = NEW.tenant_id
            ) THEN
                RAISE EXCEPTION 'control binding tenant parent mismatch';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS control_binding_tenant_parent ON control_evidence_binding",
        """
        CREATE TRIGGER control_binding_tenant_parent
        BEFORE INSERT OR UPDATE OF tenant_id, evidence_record_id
        ON control_evidence_binding
        FOR EACH ROW EXECUTE FUNCTION enforce_control_binding_tenant_parent()
        """,
        """
        CREATE OR REPLACE FUNCTION prevent_control_history_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS control_definition_version_immutable ON control_definition_version",
        """
        CREATE TRIGGER control_definition_version_immutable
        BEFORE UPDATE OR DELETE ON control_definition_version
        FOR EACH ROW EXECUTE FUNCTION prevent_control_history_mutation()
        """,
        "DROP TRIGGER IF EXISTS control_requirement_mapping_immutable ON control_requirement_mapping",
        """
        CREATE TRIGGER control_requirement_mapping_immutable
        BEFORE UPDATE OR DELETE ON control_requirement_mapping
        FOR EACH ROW EXECUTE FUNCTION prevent_control_history_mutation()
        """,
        "DROP TRIGGER IF EXISTS control_test_execution_immutable ON control_test_execution",
        """
        CREATE TRIGGER control_test_execution_immutable
        BEFORE UPDATE OR DELETE ON control_test_execution
        FOR EACH ROW EXECUTE FUNCTION prevent_control_history_mutation()
        """,
        "DROP TRIGGER IF EXISTS control_test_result_immutable ON control_test_result",
        """
        CREATE TRIGGER control_test_result_immutable
        BEFORE UPDATE OR DELETE ON control_test_result
        FOR EACH ROW EXECUTE FUNCTION prevent_control_history_mutation()
        """,
        "DROP TRIGGER IF EXISTS evidence_usage_immutable ON evidence_usage",
        """
        CREATE TRIGGER evidence_usage_immutable
        BEFORE UPDATE OR DELETE ON evidence_usage
        FOR EACH ROW EXECUTE FUNCTION prevent_control_history_mutation()
        """,
    )
