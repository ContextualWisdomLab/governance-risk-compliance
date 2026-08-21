"""Append-only audit of authorized GRC actions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.models import AuditEvent


AUDIT_EVENT_COUNT_INFO_KEY = "cwl_grc.audit_event_count"


def record_audit_event(
    session: Session,
    decision: AuthorizationDecision,
    action_name: str,
    resource_kind: str,
    resource_identifier: str,
) -> AuditEvent:
    """Append one audit event for an authorized tenant-scoped action."""
    session.info[AUDIT_EVENT_COUNT_INFO_KEY] = (
        session.info.get(AUDIT_EVENT_COUNT_INFO_KEY, 0) + 1
    )
    event = AuditEvent(
        audit_event_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        actor_identifier=decision.actor_identifier,
        purpose_code=decision.purpose_code.value,
        action_name=action_name,
        resource_kind=resource_kind,
        resource_identifier=resource_identifier,
        recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(event)
    return event
