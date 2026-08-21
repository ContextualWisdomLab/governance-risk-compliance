"""Collect, submit, and independently review tenant-scoped evidence requests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.models import EvidenceRecord, EvidenceRequest


def next_action_for_evidence_request(request_state: str) -> str:
    """Return the deterministic officer action for one request state."""
    return {
        "requested": "Collect the named fields from the assigned contributor.",
        "submitted": "Review the submitted evidence against the requested scope and period.",
        "accepted": "Reuse the accepted evidence only under its declared reuse policy.",
        "rejected": "Request a corrected evidence submission and retain the rejection reason.",
    }.get(request_state, "Review the evidence request state before proceeding.")


def create_evidence_request(
    session: Session,
    decision: AuthorizationDecision,
    request_title: str,
    requested_scope_type: str,
    requested_scope_reference: str,
    requested_period_from: datetime,
    requested_period_to: datetime,
    required_fields: list[str],
    contributor_reference: str,
    due_at: datetime,
    reuse_policy: str,
) -> EvidenceRequest:
    """Create one bounded request without copying or pre-authorizing evidence."""
    title = _required_text(request_title, "request title")
    scope_type = _required_text(requested_scope_type, "scope type")
    scope_reference = _required_text(requested_scope_reference, "scope reference")
    contributor = _required_text(contributor_reference, "contributor reference")
    fields = _normalize_required_fields(required_fields)
    reuse = _required_text(reuse_policy, "reuse policy")
    if reuse not in {"single_use", "reusable"}:
        raise HTTPException(status_code=400, detail="Use single_use or reusable evidence reuse policy.")
    period_from = _normalize_utc(requested_period_from)
    period_to = _normalize_utc(requested_period_to)
    deadline = _normalize_utc(due_at)
    if period_to < period_from:
        raise HTTPException(status_code=400, detail="The requested period must be ordered.")
    if deadline < period_to:
        raise HTTPException(status_code=400, detail="The due date cannot precede the requested period.")
    request = EvidenceRequest(
        evidence_request_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        request_title=title,
        requester_actor=decision.actor_identifier,
        requested_scope_type=scope_type,
        requested_scope_reference=scope_reference,
        requested_period_from=period_from,
        requested_period_to=period_to,
        required_fields=json.dumps(fields, ensure_ascii=False, separators=(",", ":")),
        contributor_reference=contributor,
        due_at=deadline,
        reuse_policy=reuse,
        request_state="requested",
        created_at=_utc_now(),
    )
    session.add(request)
    record_audit_event(
        session,
        decision,
        action_name="create_evidence_request",
        resource_kind="evidence_request",
        resource_identifier=request.evidence_request_id,
    )
    session.flush()
    return request


def list_evidence_requests(
    session: Session,
    decision: AuthorizationDecision,
) -> list[EvidenceRequest]:
    """List only the exact tenant's request metadata in due-date order."""
    return (
        session.query(EvidenceRequest)
        .filter_by(tenant_id=decision.tenant_id)
        .order_by(EvidenceRequest.due_at, EvidenceRequest.evidence_request_id)
        .all()
    )


def submit_evidence_request(
    session: Session,
    decision: AuthorizationDecision,
    evidence_request_id: str,
    evidence_record_id: str,
) -> EvidenceRequest:
    """Attach one same-tenant evidence record to a request exactly once."""
    request = _get_request(session, decision, evidence_request_id)
    if request.request_state != "requested":
        raise HTTPException(status_code=409, detail="That evidence request is not awaiting submission.")
    if request.contributor_reference != decision.actor_identifier:
        raise HTTPException(status_code=403, detail="This request is assigned to another contributor.")
    evidence = (
        session.query(EvidenceRecord)
        .filter_by(
            tenant_id=decision.tenant_id,
            evidence_record_id=evidence_record_id,
        )
        .one_or_none()
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="That evidence artifact is not on file.")
    request.evidence_record_id = evidence.evidence_record_id
    request.submitted_by_actor = decision.actor_identifier
    request.submitted_at = _utc_now()
    request.request_state = "submitted"
    record_audit_event(
        session,
        decision,
        action_name="submit_evidence_request",
        resource_kind="evidence_request",
        resource_identifier=request.evidence_request_id,
    )
    session.flush()
    return request


def review_evidence_request(
    session: Session,
    decision: AuthorizationDecision,
    evidence_request_id: str,
    decision_code: str,
    rejection_reason: str | None = None,
) -> EvidenceRequest:
    """Accept or reject a submitted request through a different review actor."""
    request = _get_request(session, decision, evidence_request_id)
    if request.request_state != "submitted":
        raise HTTPException(status_code=409, detail="That evidence request is not awaiting review.")
    if request.submitted_by_actor == decision.actor_identifier:
        raise HTTPException(status_code=403, detail="The contributor cannot review their own submission.")
    if decision_code not in {"accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="Choose accepted or rejected review decision.")
    reason = None
    if decision_code == "rejected":
        reason = _required_text(rejection_reason, "rejection reason")
    request.reviewed_by_actor = decision.actor_identifier
    request.reviewed_at = _utc_now()
    request.rejection_reason = reason
    request.accepted_at = _utc_now() if decision_code == "accepted" else None
    request.request_state = decision_code
    record_audit_event(
        session,
        decision,
        action_name=f"{decision_code}_evidence_request",
        resource_kind="evidence_request",
        resource_identifier=request.evidence_request_id,
    )
    session.flush()
    return request


def _get_request(
    session: Session,
    decision: AuthorizationDecision,
    evidence_request_id: str,
) -> EvidenceRequest:
    """Return one exact-tenant request or hide its existence."""
    request = (
        session.query(EvidenceRequest)
        .filter_by(
            evidence_request_id=evidence_request_id,
            tenant_id=decision.tenant_id,
        )
        .one_or_none()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="That evidence request is not on file.")
    return request


def _required_text(value: object, field_name: str) -> str:
    """Require one non-empty text field at the workflow boundary."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"Name the {field_name}.")
    return value.strip()


def _normalize_required_fields(value: object) -> list[str]:
    """Validate and normalize metadata-only requested field names."""
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=400, detail="Name at least one required evidence field.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise HTTPException(status_code=400, detail="Required evidence fields must be text.")
    fields = [item.strip() for item in value]
    if len(set(fields)) != len(fields):
        raise HTTPException(status_code=400, detail="Required evidence fields must be unique.")
    return fields


def _normalize_utc(value: datetime) -> datetime:
    """Store request timestamps as naive UTC values used by the schema."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_now() -> datetime:
    """Return the current UTC timestamp in the product's timestamp format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
