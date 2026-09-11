"""Create evidence artifacts and bind them to official controls."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.catalog import FrameworkCode, get_control_item
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.models import ControlEvidenceBinding, EvidenceRecord


def create_evidence_record(
    session: Session,
    cipher: EvidenceCipher,
    decision: AuthorizationDecision,
    evidence_title: str,
    payload_text: str,
) -> EvidenceRecord:
    """Store one evidence artifact under a purpose-limited actor."""
    title = evidence_title.strip()
    payload = payload_text.strip()
    if not title or not payload:
        raise HTTPException(status_code=400, detail="Evidence needs a title and the next artifact text.")
    record = EvidenceRecord(
        evidence_record_id=uuid4().hex,
        evidence_title=title,
        tenant_identifier=decision.tenant_identifier,
        collector_actor=decision.actor_identifier,
        purpose_code=decision.purpose_code.value,
        ciphertext_payload=cipher.encrypt(payload),
        collected_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(record)
    record_audit_event(
        session,
        decision,
        action_name="create_evidence",
        resource_kind="evidence_record",
        resource_identifier=record.evidence_record_id,
    )
    session.flush()
    return record


def bind_control_evidence(
    session: Session,
    decision: AuthorizationDecision,
    framework: FrameworkCode,
    catalog_identifier: str,
    evidence_record_id: str,
) -> ControlEvidenceBinding:
    """Bind an evidence artifact to one official control identifier."""
    control = get_control_item(session, framework, catalog_identifier)
    if control is None:
        raise HTTPException(status_code=404, detail="That official control is not in the catalog.")
    evidence = session.get(EvidenceRecord, evidence_record_id)
    if evidence is None or evidence.tenant_identifier != decision.tenant_identifier:
        raise HTTPException(status_code=404, detail="That evidence artifact is not on file.")
    binding = ControlEvidenceBinding(
        binding_id=uuid4().hex,
        control_item_id=control.control_item_id,
        evidence_record_id=evidence.evidence_record_id,
        bound_by_actor=decision.actor_identifier,
        purpose_code=decision.purpose_code.value,
        bound_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(binding)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="That evidence is already bound to this control.") from exc
    record_audit_event(
        session,
        decision,
        action_name="bind_evidence",
        resource_kind="control_evidence_binding",
        resource_identifier=binding.binding_id,
    )
    return binding
