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
    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    policy_columns = {
        column["name"]
        for column in inspect(engine).get_columns("policy_document")
    }
    version_columns = {
        column["name"]
        for column in inspect(engine).get_columns("policy_version")
    }
    assert "current_version_number" in policy_columns
    assert "is_finalized" in version_columns
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
    assert counter == 3
    assert finalized in {True, 1}
    assert receipt_count == 2


def test_catalog_migration_adds_release_link_to_existing_framework(
    tmp_path: Path,
) -> None:
    """The provenance migration upgrades a pre-provenance framework table."""
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-legacy.sqlite'}")
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
        connection.execute(
            text(
                "CREATE TABLE catalog_release ("
                "catalog_release_id VARCHAR(64) PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE control_framework ("
                "framework_code VARCHAR(64) PRIMARY KEY)"
            )
        )
    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    framework_columns = {
        column["name"]
        for column in inspect(engine).get_columns("control_framework")
    }
    assert "catalog_release_id" in framework_columns
    with engine.connect() as connection:
        receipt_count = connection.execute(
            text("SELECT COUNT(*) FROM schema_migration")
        ).scalar_one()
    assert receipt_count == 2


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
