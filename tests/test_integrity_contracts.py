"""Regression contracts for durable GRC evidence and policy integrity."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, inspect, text, update
from sqlalchemy.exc import DBAPIError

from cwl_grc import create_app
from cwl_grc.authorization import (
    AuthorizationDecision,
    PurposeCode,
    seed_authorization_purposes,
)
from cwl_grc.catalog import (
    FrameworkCode,
    framework_source_url,
    seed_control_catalog,
)
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.migrations import (
    apply_schema_migrations,
    integrity_guard_statements,
)
from cwl_grc.models import (
    AuditEvent,
    PolicyControlMapping,
    PolicyDocument,
    PolicyVersion,
)
from cwl_grc.policy import ControlRef, author_policy, revise_policy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _seeded_policy_factory(database_url: str = "sqlite://"):  # noqa: ANN202
    """Return a product store containing one finalized policy edition."""
    factory = create_session_factory(database_url)
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        document = author_policy(
            session,
            AuthorizationDecision(
                "officer-integrity",
                PurposeCode.POLICY_AUTHORING,
            ),
            "Integrity Policy",
            "The first edition is immutable after publication.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        document_id = document.policy_document_id
        session.commit()
    return factory, document_id


def test_product_workflow_rejects_any_dirty_tree() -> None:
    """CI rejects tracked or untracked changes, not only whitespace errors."""
    workflow = (
        REPOSITORY_ROOT / ".github/workflows/product.yml"
    ).read_text(encoding="utf-8")
    assert "git diff --check" in workflow
    assert 'test -z "$(git status --porcelain)"' in workflow


def test_architecture_uses_the_registered_health_route() -> None:
    """Architecture diagrams name the exact route registered by FastAPI."""
    architecture = (REPOSITORY_ROOT / "ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    assert "probe[/healthz]" in architecture
    assert "probe[/healthz/]" not in architecture


def test_csap_source_is_pinned_to_the_2026_07_kisa_notice() -> None:
    """The catalog identifies the official KISA notice for the stored edition."""
    source = framework_source_url(FrameworkCode.CSAP_2026)
    assert "selectGnrlVrtlRcsrmList.do" in source
    assert "%ED%81%B4%EB%9D%BC%EC%9A%B0%EB%93%9C" in source
    assert "/main/csap/intro/" not in source


def test_evidence_cipher_requires_an_explicit_ephemeral_mode() -> None:
    """Missing durable key material fails unless an in-memory test opts in."""
    with pytest.raises(ValueError, match="evidence key"):
        EvidenceCipher(None)
    cipher = EvidenceCipher(None, allow_ephemeral=True)
    assert cipher.decrypt(cipher.encrypt("exact operational evidence")) == (
        "exact operational evidence"
    )


def test_persistent_database_cannot_start_without_an_evidence_key(
    tmp_path: Path,
) -> None:
    """A durable store never starts with an unrecoverable random evidence key."""
    database_url = f"sqlite:///{tmp_path / 'persistent.sqlite'}"
    with pytest.raises(ValueError, match="evidence key"):
        create_app(database_url=database_url, evidence_key=None)


def test_audit_events_reject_update_and_delete_at_database_boundary() -> None:
    """Database triggers preserve append-only audit history."""
    factory, _document_id = _seeded_policy_factory()
    with factory() as session:
        event_id = session.query(AuditEvent.audit_event_id).first()[0]
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(
                update(AuditEvent)
                .where(AuditEvent.audit_event_id == event_id)
                .values(action_name="tampered")
            )
        session.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(
                delete(AuditEvent).where(AuditEvent.audit_event_id == event_id)
            )


def test_finalized_policy_editions_and_mappings_reject_mutation() -> None:
    """Published policy text and its control set remain immutable in SQL."""
    factory, _document_id = _seeded_policy_factory()
    with factory() as session:
        version = session.query(PolicyVersion).one()
        mapping = session.query(PolicyControlMapping).one()
        assert version.is_finalized is True
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                update(PolicyVersion)
                .where(
                    PolicyVersion.policy_version_id
                    == version.policy_version_id
                )
                .values(policy_body="tampered")
            )
        session.rollback()
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                delete(PolicyControlMapping).where(
                    PolicyControlMapping.mapping_id == mapping.mapping_id
                )
            )
        session.rollback()
        session.add(
            PolicyControlMapping(
                mapping_id=uuid4().hex,
                policy_version_id=version.policy_version_id,
                control_item_id=mapping.control_item_id,
            )
        )
        with pytest.raises(DBAPIError, match="finalized"):
            session.commit()


def test_stale_concurrent_policy_revision_returns_conflict(tmp_path: Path) -> None:
    """Two writers cannot allocate the same next policy version number."""
    factory, document_id = _seeded_policy_factory(
        f"sqlite:///{tmp_path / 'concurrent.sqlite'}"
    )
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
            AuthorizationDecision(
                "officer-first",
                PurposeCode.POLICY_AUTHORING,
            ),
            document_id,
            "The second edition wins the optimistic allocation.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        first.commit()
        with pytest.raises(HTTPException) as conflict:
            revise_policy(
                stale,
                AuthorizationDecision(
                    "officer-stale",
                    PurposeCode.POLICY_AUTHORING,
                ),
                document_id,
                "This stale writer must retry from the new current edition.",
                [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
            )
        assert conflict.value.status_code == 409
    finally:
        first.close()
        stale.close()


def test_schema_migration_upgrades_legacy_tables_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """A pre-integrity SQLite store receives counters and finalization state."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE policy_document ("
                "policy_document_id VARCHAR(64) PRIMARY KEY, "
                "policy_title VARCHAR(255) NOT NULL, "
                "created_by_actor VARCHAR(128) NOT NULL, "
                "created_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE policy_version ("
                "policy_version_id VARCHAR(64) PRIMARY KEY, "
                "policy_document_id VARCHAR(64) NOT NULL, "
                "version_number INTEGER NOT NULL, "
                "policy_body TEXT NOT NULL, "
                "authored_by_actor VARCHAR(128) NOT NULL, "
                "authored_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_document VALUES "
                "('policy-1', 'Legacy', 'officer', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_version VALUES "
                "('version-1', 'policy-1', 3, 'Legacy body', "
                "'officer', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE evidence_record ("
                "evidence_record_id VARCHAR(64) PRIMARY KEY, "
                "evidence_title VARCHAR(255) NOT NULL, "
                "collector_actor VARCHAR(128) NOT NULL, "
                "purpose_code VARCHAR(64) NOT NULL, "
                "ciphertext_payload BLOB NOT NULL, "
                "collected_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evidence_record VALUES "
                "('evidence-1', 'Legacy register', 'officer', "
                "'evidence_binding', X'00', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE audit_event ("
                "audit_event_id VARCHAR(64) PRIMARY KEY, "
                "actor_identifier VARCHAR(128) NOT NULL, "
                "purpose_code VARCHAR(64) NOT NULL, "
                "action_name VARCHAR(64) NOT NULL, "
                "resource_kind VARCHAR(64) NOT NULL, "
                "resource_identifier VARCHAR(128) NOT NULL, "
                "recorded_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_event VALUES "
                "('audit-1', 'officer', 'policy_authoring', "
                "'author_policy', 'policy_document', 'policy-1', "
                "CURRENT_TIMESTAMP)"
            )
        )
    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    inspector = inspect(engine)
    policy_columns = {column["name"] for column in inspector.get_columns("policy_document")}
    version_columns = {column["name"] for column in inspector.get_columns("policy_version")}
    evidence_columns = {column["name"] for column in inspector.get_columns("evidence_record")}
    audit_columns = {column["name"] for column in inspector.get_columns("audit_event")}
    assert "current_version_number" in policy_columns
    assert "tenant_identifier" in policy_columns
    assert "is_finalized" in version_columns
    assert "tenant_identifier" in evidence_columns
    assert "tenant_identifier" in audit_columns
    assert "issuer_identifier" in audit_columns
    assert "client_identifier" in audit_columns
    assert "correlation_reference" in audit_columns
    assert "decision_outcome" in audit_columns
    index_names = {
        index["name"]
        for table_name in ("policy_document", "evidence_record", "audit_event")
        for index in inspector.get_indexes(table_name)
    }
    assert "policy_document_tenant_actor" in index_names
    assert "evidence_record_tenant_actor" in index_names
    assert "audit_event_tenant_correlation" in index_names
    with engine.connect() as connection:
        counter = connection.execute(
            text(
                "SELECT current_version_number FROM policy_document "
                "WHERE policy_document_id = 'policy-1'"
            )
        ).scalar_one()
        finalized = connection.execute(
            text(
                "SELECT is_finalized FROM policy_version "
                "WHERE policy_version_id = 'version-1'"
            )
        ).scalar_one()
        receipt_count = connection.execute(
            text("SELECT COUNT(*) FROM schema_migration")
        ).scalar_one()
        tenant = connection.execute(
            text(
                "SELECT tenant_identifier FROM policy_document "
                "WHERE policy_document_id = 'policy-1'"
            )
        ).scalar_one()
        evidence_tenant = connection.execute(
            text(
                "SELECT tenant_identifier FROM evidence_record "
                "WHERE evidence_record_id = 'evidence-1'"
            )
        ).scalar_one()
        audit_tenant = connection.execute(
            text(
                "SELECT tenant_identifier FROM audit_event "
                "WHERE audit_event_id = 'audit-1'"
            )
        ).scalar_one()
        audit_attribution = connection.execute(
            text(
                "SELECT issuer_identifier, client_identifier, "
                "correlation_reference, decision_outcome FROM audit_event "
                "WHERE audit_event_id = 'audit-1'"
            )
        ).one()
    assert counter == 3
    assert finalized in {True, 1}
    assert receipt_count == 3
    assert tenant == "local_preview"
    assert evidence_tenant == "local_preview"
    assert audit_tenant == "local_preview"
    assert audit_attribution == (
        "local_preview",
        "local_preview",
        "legacy_unattributed",
        "allow",
    )


def test_tenant_ownership_migration_skips_tables_that_are_not_present(
    tmp_path: Path,
) -> None:
    """0002 records a receipt when a partial store has not created owned tables yet."""
    engine = create_engine(f"sqlite:///{tmp_path / 'partial.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_migration ("
                "migration_key VARCHAR(64) PRIMARY KEY, "
                "applied_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO schema_migration VALUES "
                "('0001_policy_integrity', CURRENT_TIMESTAMP)"
            )
        )
    apply_schema_migrations(engine)
    with engine.connect() as connection:
        keys = {
            row[0]
            for row in connection.execute(
                text("SELECT migration_key FROM schema_migration")
            )
        }
    assert keys == {
        "0001_policy_integrity",
        "0002_tenant_ownership",
        "0003_audit_attribution",
    }


def test_audit_attribution_migration_skips_existing_columns(
    tmp_path: Path,
) -> None:
    """0003 is idempotent when issuer, client, correlation, and decision already exist."""
    engine = create_engine(f"sqlite:///{tmp_path / 'attributed.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_migration ("
                "migration_key VARCHAR(64) PRIMARY KEY, "
                "applied_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO schema_migration VALUES "
                "('0001_policy_integrity', CURRENT_TIMESTAMP), "
                "('0002_tenant_ownership', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE audit_event ("
                "audit_event_id VARCHAR(64) PRIMARY KEY, "
                "tenant_identifier VARCHAR(128) NOT NULL, "
                "actor_identifier VARCHAR(128) NOT NULL, "
                "purpose_code VARCHAR(64) NOT NULL, "
                "action_name VARCHAR(64) NOT NULL, "
                "resource_kind VARCHAR(64) NOT NULL, "
                "resource_identifier VARCHAR(128) NOT NULL, "
                "recorded_at TIMESTAMP NOT NULL, "
                "issuer_identifier VARCHAR(1024) NOT NULL, "
                "client_identifier VARCHAR(128) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_event VALUES ("
                "'audit-2', 'local_preview', 'officer', 'policy_authoring', "
                "'author_policy', 'policy_document', 'policy-1', "
                "CURRENT_TIMESTAMP, 'local_preview', 'local_preview')"
            )
        )
    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("audit_event")}
    assert "correlation_reference" in columns
    assert "decision_outcome" in columns
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT correlation_reference, decision_outcome "
                "FROM audit_event WHERE audit_event_id = 'audit-2'"
            )
        ).one()
        keys = {
            item[0]
            for item in connection.execute(text("SELECT migration_key FROM schema_migration"))
        }
    assert row == ("legacy_unattributed", "allow")
    assert "0003_audit_attribution" in keys


def test_audit_attribution_migration_keeps_existing_attribution_values(
    tmp_path: Path,
) -> None:
    """0003 does not rewrite issuer, client, correlation, or decision when present."""
    engine = create_engine(f"sqlite:///{tmp_path / 'complete-audit.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_migration ("
                "migration_key VARCHAR(64) PRIMARY KEY, "
                "applied_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO schema_migration VALUES "
                "('0001_policy_integrity', CURRENT_TIMESTAMP), "
                "('0002_tenant_ownership', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE audit_event ("
                "audit_event_id VARCHAR(64) PRIMARY KEY, "
                "tenant_identifier VARCHAR(128) NOT NULL, "
                "actor_identifier VARCHAR(128) NOT NULL, "
                "purpose_code VARCHAR(64) NOT NULL, "
                "action_name VARCHAR(64) NOT NULL, "
                "resource_kind VARCHAR(64) NOT NULL, "
                "resource_identifier VARCHAR(128) NOT NULL, "
                "recorded_at TIMESTAMP NOT NULL, "
                "issuer_identifier VARCHAR(1024) NOT NULL, "
                "client_identifier VARCHAR(128) NOT NULL, "
                "correlation_reference VARCHAR(128) NOT NULL, "
                "decision_outcome VARCHAR(32) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_event VALUES ("
                "'audit-3', 'tenant-acme', 'officer-park', 'policy_authoring', "
                "'author_policy', 'policy_document', 'policy-1', "
                "CURRENT_TIMESTAMP, 'https://identity.example.test/realms/cwl', "
                "'cwl-grc-web', 'kept-correlation', 'allow')"
            )
        )
    apply_schema_migrations(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT issuer_identifier, client_identifier, "
                "correlation_reference, decision_outcome "
                "FROM audit_event WHERE audit_event_id = 'audit-3'"
            )
        ).one()
    assert row == (
        "https://identity.example.test/realms/cwl",
        "cwl-grc-web",
        "kept-correlation",
        "allow",
    )


def test_integrity_guard_ddl_covers_supported_and_unknown_dialects() -> None:
    """SQLite and PostgreSQL get guards; unknown stores fail closed."""
    sqlite_ddl = "\n".join(integrity_guard_statements("sqlite"))
    postgres_ddl = "\n".join(integrity_guard_statements("postgresql"))
    assert "audit_event_block_update" in sqlite_ddl
    assert "policy_control_mapping_require_open_version" in sqlite_ddl
    assert "prevent_audit_event_mutation" in postgres_ddl
    assert "prevent_policy_mapping_mutation" in postgres_ddl
    with pytest.raises(ValueError, match="Unsupported GRC database dialect"):
        integrity_guard_statements("mysql")
