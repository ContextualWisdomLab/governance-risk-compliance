"""Append-only audit of authorized GRC actions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from cwl_grc.authorization import AuthorizationDecision, DECISION_ALLOW
from cwl_grc.correlation import (
    current_correlation_reference,
    looks_like_access_token,
    normalize_correlation_reference,
)
from cwl_grc.models import AuditEvent


def record_audit_event(
    session: Session,
    decision: AuthorizationDecision,
    action_name: str,
    resource_kind: str,
    resource_identifier: str,
) -> AuditEvent:
    """Append one attributed audit event without copying Keyverse access tokens."""
    event = AuditEvent(
        audit_event_id=uuid4().hex,
        tenant_identifier=_safe_attribution_text(
            decision.tenant_identifier,
            "tenant identifier",
        ),
        actor_identifier=_safe_attribution_text(
            decision.actor_identifier,
            "actor identifier",
        ),
        purpose_code=decision.purpose_code.value,
        action_name=action_name,
        resource_kind=resource_kind,
        resource_identifier=resource_identifier,
        recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
        issuer_identifier=_safe_attribution_text(
            decision.issuer_identifier,
            "issuer identifier",
        ),
        client_identifier=_safe_attribution_text(
            decision.client_identifier,
            "client identifier",
        ),
        correlation_reference=_audit_correlation_reference(
            decision.correlation_reference
        ),
        decision_outcome=_decision_outcome(decision.decision_outcome),
    )
    session.add(event)
    return event


def _audit_correlation_reference(value: str) -> str:
    """Persist a request correlation reference, never compact JWT material."""
    candidate = value.strip() if value else current_correlation_reference()
    if looks_like_access_token(candidate):
        raise ValueError("Audit events cannot store access-token material.")
    return normalize_correlation_reference(candidate)


def _safe_attribution_text(value: str, label: str) -> str:
    """Reject attribution fields that copy compact JWT access-token material."""
    if not value or value != value.strip() or looks_like_access_token(value):
        raise ValueError(f"The audit {label} cannot store access-token material.")
    return value


def _decision_outcome(value: str) -> str:
    """Persist the authorization decision without accepting empty outcomes."""
    outcome = (value or "").strip() or DECISION_ALLOW
    if outcome != DECISION_ALLOW:
        raise ValueError("Audit events record only authorized allow decisions.")
    return outcome
