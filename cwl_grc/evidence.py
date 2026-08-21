"""Create evidence artifacts and bind them to official controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.catalog import FrameworkCode, get_control_item
from cwl_grc.encryption import (
    EncryptedEvidence,
    EvidenceCipher,
    EvidenceDecryptionError,
    make_evidence_context,
)
from cwl_grc.models import ControlEvidenceBinding, EvidenceRecord


@dataclass(frozen=True)
class EvidenceRewrapResult:
    """Report one bounded, resumable evidence-key rewrap pass."""

    scanned_count: int
    rewrapped_count: int
    failed_count: int
    failed_record_ids: tuple[str, ...]
    last_scanned_record_id: str | None


def create_evidence_record(
    session: Session,
    cipher: EvidenceCipher,
    decision: AuthorizationDecision,
    evidence_title: str,
    payload_text: str,
) -> EvidenceRecord:
    """Store one evidence artifact under an exact tenant and purpose-limited actor."""
    title = evidence_title.strip()
    payload = payload_text.strip()
    if not title or not payload:
        raise HTTPException(status_code=400, detail="Evidence needs a title and the next artifact text.")
    evidence_record_id = uuid4().hex
    encrypted = cipher.encrypt_record(
        payload,
        context=make_evidence_context(decision.tenant_id, evidence_record_id),
    )
    record = EvidenceRecord(
        evidence_record_id=evidence_record_id,
        tenant_id=decision.tenant_id,
        evidence_title=title,
        collector_actor=decision.actor_identifier,
        purpose_code=decision.purpose_code.value,
        ciphertext_payload=encrypted.ciphertext,
        encryption_key_id=encrypted.encryption_key_id,
        encryption_algorithm_version=encrypted.encryption_algorithm_version,
        encryption_context_digest=encrypted.encryption_context_digest,
        source_content_digest=encrypted.source_content_digest,
        integrity_digest=encrypted.integrity_digest,
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


def record_encryption_envelope(record: EvidenceRecord) -> EncryptedEvidence:
    """Convert persisted encryption metadata into the provider-neutral envelope type."""
    return EncryptedEvidence(
        ciphertext=record.ciphertext_payload,
        encryption_key_id=record.encryption_key_id,
        encryption_algorithm_version=record.encryption_algorithm_version,
        encryption_context_digest=record.encryption_context_digest,
        source_content_digest=record.source_content_digest,
        integrity_digest=record.integrity_digest,
    )


def rewrap_evidence_records(
    session: Session,
    cipher: EvidenceCipher,
    decision: AuthorizationDecision,
    *,
    batch_size: int = 100,
    after_record_id: str | None = None,
) -> EvidenceRewrapResult:
    """Re-encrypt one tenant batch with the active key and audit every outcome."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 0 < batch_size <= 1000:
        raise ValueError("Evidence rewrap batch size must be between 1 and 1000.")
    query = (
        session.query(EvidenceRecord)
        .filter_by(tenant_id=decision.tenant_id)
        .order_by(EvidenceRecord.evidence_record_id)
    )
    if after_record_id is not None:
        query = query.filter(EvidenceRecord.evidence_record_id > after_record_id)
    records = query.limit(batch_size).all()
    rewrapped = 0
    failed_ids: list[str] = []
    for record in records:
        try:
            context = make_evidence_context(record.tenant_id, record.evidence_record_id)
            plaintext = cipher.decrypt_record(
                record_encryption_envelope(record),
                context=context,
            )
            if (
                record.encryption_key_id == cipher.active_key_id
                and record.encryption_algorithm_version == "fernet-v1"
            ):
                continue
            encrypted = cipher.encrypt_record(plaintext, context=context)
            record.ciphertext_payload = encrypted.ciphertext
            record.encryption_key_id = encrypted.encryption_key_id
            record.encryption_algorithm_version = encrypted.encryption_algorithm_version
            record.encryption_context_digest = encrypted.encryption_context_digest
            record.source_content_digest = encrypted.source_content_digest
            record.integrity_digest = encrypted.integrity_digest
            record_audit_event(
                session,
                decision,
                action_name="rewrap_evidence",
                resource_kind="evidence_record",
                resource_identifier=record.evidence_record_id,
            )
            rewrapped += 1
        except EvidenceDecryptionError:
            failed_ids.append(record.evidence_record_id)
            record_audit_event(
                session,
                decision,
                action_name="rewrap_failed",
                resource_kind="evidence_record",
                resource_identifier=record.evidence_record_id,
            )
    session.flush()
    return EvidenceRewrapResult(
        scanned_count=len(records),
        rewrapped_count=rewrapped,
        failed_count=len(failed_ids),
        failed_record_ids=tuple(failed_ids),
        last_scanned_record_id=records[-1].evidence_record_id if records else None,
    )


def bind_control_evidence(
    session: Session,
    decision: AuthorizationDecision,
    framework: FrameworkCode,
    catalog_identifier: str,
    evidence_record_id: str,
) -> ControlEvidenceBinding:
    """Bind same-tenant evidence to one official control identifier."""
    control = get_control_item(session, framework, catalog_identifier)
    if control is None:
        raise HTTPException(status_code=404, detail="That official control is not in the catalog.")
    evidence = (
        session.query(EvidenceRecord)
        .filter_by(
            evidence_record_id=evidence_record_id,
            tenant_id=decision.tenant_id,
        )
        .one_or_none()
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="That evidence artifact is not on file.")
    binding = ControlEvidenceBinding(
        binding_id=uuid4().hex,
        tenant_id=decision.tenant_id,
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
