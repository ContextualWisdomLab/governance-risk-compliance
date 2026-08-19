"""Regression contracts for durable GRC evidence and policy integrity."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from cwl_grc import create_app
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, framework_source_url, seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.models import AuditEvent, PolicyControlMapping, PolicyDocument, PolicyVersion
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
            AuthorizationDecision("officer-integrity", PurposeCode.POLICY_AUTHORING),
            "Integrity Policy",
            "The first edition is immutable after publication.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        document_id = document.policy_document_id
        session.commit()
    return factory, document_id


def test_product_workflow_rejects_any_dirty_tree() -> None:
    """CI rejects tracked or untracked changes, not only whitespace errors."""
    workflow = (REPOSITORY_ROOT / ".github/workflows/product.yml").read_text(encoding="utf-8")
    assert "git diff --check" in workflow
    assert 'test -z "$(git status --porcelain)"' in workflow


def test_architecture_uses_the_registered_health_route() -> None:
    """Architecture diagrams name the exact route registered by FastAPI."""
    architecture = (REPOSITORY_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
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


def test_persistent_database_cannot_start_without_an_evidence_key(tmp_path: Path) -> None:
    """A durable store never starts with an unrecoverable random evidence key."""
    database_url = f"sqlite:///{tmp_path / 'persistent.sqlite'}"
    with pytest.raises(ValueError, match="evidence key"):
        create_app(database_url=database_url, evidence_key=None)


def test_audit_events_reject_update_and_delete_at_the_database_boundary() -> None:
    """Database triggers preserve append-only audit history."""
    factory, _document_id = _seeded_policy_factory()
    with factory() as session:
        event_id = session.query(AuditEvent.audit_event_id).one()[0]
        session.execute(
            update(AuditEvent)
            .where(AuditEvent.audit_event_id == event_id)
            .values(action_name="tampered")
        )
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
        session.rollback()
        session.execute(delete(AuditEvent).where(AuditEvent.audit_event_id == event_id))
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()


def test_finalized_policy_editions_and_mappings_reject_mutation() -> None:
    """Published policy text and its control set remain immutable in SQL."""
    factory, _document_id = _seeded_policy_factory()
    with factory() as session:
        version = session.query(PolicyVersion).one()
        mapping = session.query(PolicyControlMapping).one()
        assert version.is_finalized is True
        session.execute(
            update(PolicyVersion)
            .where(PolicyVersion.policy_version_id == version.policy_version_id)
            .values(policy_body="tampered")
        )
        with pytest.raises(DBAPIError, match="immutable"):
            session.commit()
        session.rollback()
        session.execute(
            delete(PolicyControlMapping).where(
                PolicyControlMapping.mapping_id == mapping.mapping_id
            )
        )
        with pytest.raises(DBAPIError, match="immutable"):
            session.commit()
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
            AuthorizationDecision("officer-first", PurposeCode.POLICY_AUTHORING),
            document_id,
            "The second edition wins the optimistic allocation.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        first.commit()
        with pytest.raises(HTTPException) as conflict:
            revise_policy(
                stale,
                AuthorizationDecision("officer-stale", PurposeCode.POLICY_AUTHORING),
                document_id,
                "This stale writer must retry from the new current edition.",
                [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
            )
        assert conflict.value.status_code == 409
    finally:
        first.close()
        stale.close()
