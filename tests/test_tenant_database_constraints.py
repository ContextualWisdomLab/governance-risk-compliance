"""Database-boundary regressions for tenant-owned GRC relationships."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from cwl_grc.authorization import PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, get_control_item, seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.models import (
    ControlEvidenceBinding,
    EvidenceRecord,
    PolicyDocument,
    PolicyVersion,
)


def _tenant_factory():  # noqa: ANN202
    """Return an isolated store with official controls and authorization purposes."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()
    return factory


def test_database_rejects_policy_version_with_cross_tenant_parent() -> None:
    """A child policy edition cannot point at another tenant's policy identity."""
    factory = _tenant_factory()
    document_id = uuid4().hex
    with factory() as session:
        session.add(
            PolicyDocument(
                policy_document_id=document_id,
                tenant_id="tenant-a",
                policy_title="Tenant A access policy",
                created_by_actor="officer-a",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                current_version_number=0,
            )
        )
        session.commit()

    with factory() as session:
        session.add(
            PolicyVersion(
                policy_version_id=uuid4().hex,
                tenant_id="tenant-b",
                policy_document_id=document_id,
                version_number=1,
                policy_body="Cross-tenant edition must never persist.",
                authored_by_actor="officer-b",
                authored_at=datetime.now(timezone.utc).replace(tzinfo=None),
                is_finalized=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_rejects_evidence_binding_with_cross_tenant_parent() -> None:
    """A binding cannot claim evidence that belongs to another tenant."""
    factory = _tenant_factory()
    evidence_id = uuid4().hex
    cipher = EvidenceCipher(None, allow_ephemeral=True)
    with factory() as session:
        control = get_control_item(session, FrameworkCode.SOC2_TSC_2017, "CC1.1")
        assert control is not None
        control_item_id = control.control_item_id
        session.add(
            EvidenceRecord(
                evidence_record_id=evidence_id,
                tenant_id="tenant-a",
                evidence_title="Tenant A access review",
                collector_actor="officer-a",
                purpose_code=PurposeCode.EVIDENCE_BINDING.value,
                ciphertext_payload=cipher.encrypt("Exact tenant A evidence."),
                collected_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        session.commit()

    with factory() as session:
        session.add(
            ControlEvidenceBinding(
                binding_id=uuid4().hex,
                tenant_id="tenant-b",
                control_item_id=control_item_id,
                evidence_record_id=evidence_id,
                bound_by_actor="officer-b",
                purpose_code=PurposeCode.EVIDENCE_BINDING.value,
                bound_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
