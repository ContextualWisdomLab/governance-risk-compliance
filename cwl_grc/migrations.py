"""Versioned schema upgrades and database-enforced immutability guards."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Connection, Engine, inspect, text


POLICY_INTEGRITY_MIGRATION = "0001_policy_integrity"
CATALOG_PROVENANCE_MIGRATION = "0002_catalog_provenance"
CATALOG_RELEASE_RECEIPT_LINK_MIGRATION = "0003_catalog_release_receipt_link"


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
        applied = {
            row[0]
            for row in connection.execute(text("SELECT migration_key FROM schema_migration"))
        }
        if POLICY_INTEGRITY_MIGRATION not in applied:
            _apply_policy_integrity_migration(connection)
        if CATALOG_PROVENANCE_MIGRATION not in applied:
            _apply_catalog_provenance_migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES (:migration_key, :applied_at)"
                ),
                {
                    "migration_key": CATALOG_PROVENANCE_MIGRATION,
                    "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
            )
        if CATALOG_RELEASE_RECEIPT_LINK_MIGRATION not in applied:
            _apply_catalog_release_receipt_link_migration(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migration (migration_key, applied_at) "
                    "VALUES (:migration_key, :applied_at)"
                ),
                {
                    "migration_key": CATALOG_RELEASE_RECEIPT_LINK_MIGRATION,
                    "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
            )


def _apply_policy_integrity_migration(connection: Connection) -> None:
    """Upgrade legacy policy columns and record the first migration receipt."""
    inspector = inspect(connection)
    if not {"policy_document", "policy_version"}.issubset(inspector.get_table_names()):
        return
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


def _apply_catalog_provenance_migration(connection: Connection) -> None:
    """Upgrade an existing control framework with the optional release link."""
    inspector = inspect(connection)
    if "control_framework" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("control_framework")}
    if "catalog_release_id" not in columns:
        connection.execute(
            text(
                "ALTER TABLE control_framework ADD COLUMN catalog_release_id "
                "VARCHAR(64) REFERENCES catalog_release (catalog_release_id)"
            )
        )


def _apply_catalog_release_receipt_link_migration(connection: Connection) -> None:
    """Bind existing catalog releases to their latest successful receipt when possible."""
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "catalog_release" not in table_names:
        return
    columns = {column["name"] for column in inspector.get_columns("catalog_release")}
    if "catalog_import_run_id" not in columns:
        connection.execute(
            text(
                "ALTER TABLE catalog_release ADD COLUMN catalog_import_run_id "
                "VARCHAR(64) REFERENCES catalog_import_run (catalog_import_run_id)"
            )
        )
        columns.add("catalog_import_run_id")
    if not {
        "catalog_import_run",
        "catalog_import_receipt",
    }.issubset(table_names) or "source_artifact_version_id" not in columns:
        return
    connection.execute(
        text(
            """
            UPDATE catalog_release
            SET catalog_import_run_id = (
                SELECT catalog_import_run.catalog_import_run_id
                FROM catalog_import_run
                JOIN catalog_import_receipt
                  ON catalog_import_receipt.catalog_import_run_id =
                     catalog_import_run.catalog_import_run_id
                WHERE catalog_import_run.source_artifact_version_id =
                      catalog_release.source_artifact_version_id
                  AND catalog_import_run.run_status = 'succeeded'
                ORDER BY catalog_import_run.completed_at DESC,
                         catalog_import_run.catalog_import_run_id DESC
                LIMIT 1
            )
            WHERE catalog_import_run_id IS NULL
            """
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
        """
        CREATE TRIGGER IF NOT EXISTS source_artifact_version_block_update
        BEFORE UPDATE ON source_artifact_version
        BEGIN
            SELECT RAISE(ABORT, 'source_artifact_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS source_artifact_version_block_delete
        BEFORE DELETE ON source_artifact_version
        BEGIN
            SELECT RAISE(ABORT, 'source_artifact_version is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_import_run_block_update
        BEFORE UPDATE ON catalog_import_run
        BEGIN
            SELECT RAISE(ABORT, 'catalog_import_run is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_import_run_block_delete
        BEFORE DELETE ON catalog_import_run
        BEGIN
            SELECT RAISE(ABORT, 'catalog_import_run is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_import_receipt_block_update
        BEFORE UPDATE ON catalog_import_receipt
        BEGIN
            SELECT RAISE(ABORT, 'catalog_import_receipt is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_import_receipt_block_delete
        BEFORE DELETE ON catalog_import_receipt
        BEGIN
            SELECT RAISE(ABORT, 'catalog_import_receipt is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_release_block_update
        BEFORE UPDATE ON catalog_release
        BEGIN
            SELECT RAISE(ABORT, 'catalog_release is immutable');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_release_require_matching_import_version
        BEFORE INSERT ON catalog_release
        WHEN NEW.catalog_import_run_id IS NOT NULL
         AND NOT EXISTS (
            SELECT 1
            FROM catalog_import_run
            WHERE catalog_import_run_id = NEW.catalog_import_run_id
              AND source_artifact_version_id = NEW.source_artifact_version_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'catalog_release import run version mismatch');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS catalog_release_block_delete
        BEFORE DELETE ON catalog_release
        BEGIN
            SELECT RAISE(ABORT, 'catalog_release is immutable');
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
        """
        CREATE OR REPLACE FUNCTION prevent_catalog_provenance_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS source_artifact_version_immutable ON source_artifact_version",
        "DROP TRIGGER IF EXISTS catalog_import_run_immutable ON catalog_import_run",
        "DROP TRIGGER IF EXISTS catalog_import_receipt_immutable ON catalog_import_receipt",
        "DROP TRIGGER IF EXISTS catalog_release_immutable ON catalog_release",
        """
        CREATE TRIGGER source_artifact_version_immutable
        BEFORE UPDATE OR DELETE ON source_artifact_version
        FOR EACH ROW EXECUTE FUNCTION prevent_catalog_provenance_mutation()
        """,
        """
        CREATE TRIGGER catalog_import_run_immutable
        BEFORE UPDATE OR DELETE ON catalog_import_run
        FOR EACH ROW EXECUTE FUNCTION prevent_catalog_provenance_mutation()
        """,
        """
        CREATE TRIGGER catalog_import_receipt_immutable
        BEFORE UPDATE OR DELETE ON catalog_import_receipt
        FOR EACH ROW EXECUTE FUNCTION prevent_catalog_provenance_mutation()
        """,
        """
        CREATE TRIGGER catalog_release_immutable
        BEFORE UPDATE OR DELETE ON catalog_release
        FOR EACH ROW EXECUTE FUNCTION prevent_catalog_provenance_mutation()
        """,
        """
        CREATE OR REPLACE FUNCTION validate_catalog_release_import_version()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.catalog_import_run_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                   FROM catalog_import_run
                   WHERE catalog_import_run_id = NEW.catalog_import_run_id
                     AND source_artifact_version_id = NEW.source_artifact_version_id
               ) THEN
                RAISE EXCEPTION 'catalog_release import run version mismatch';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS catalog_release_import_version_guard ON catalog_release",
        """
        CREATE TRIGGER catalog_release_import_version_guard
        BEFORE INSERT ON catalog_release
        FOR EACH ROW EXECUTE FUNCTION validate_catalog_release_import_version()
        """,
    )
