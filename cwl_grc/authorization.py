"""Purpose-limited authorization for policy and evidence work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from fastapi import HTTPException
from sqlalchemy.orm import Session

from cwl_grc.models import AuthorizationPurpose


LOCAL_DEVELOPMENT_TENANT = "local_development"


class PurposeCode(StrEnum):
    """Declared purposes that may touch GRC records."""

    COVERAGE_REVIEW = "coverage_review"
    COMPLIANCE_GOVERNANCE = "compliance_governance"
    EVIDENCE_BINDING = "evidence_binding"
    EVIDENCE_RETENTION = "evidence_retention"
    HEALTH_PROBE = "health_probe"
    POLICY_AUTHORING = "policy_authoring"


@dataclass(frozen=True)
class AuthorizationDecision:
    """An actor acting for one exact tenant under one declared purpose."""

    actor_identifier: str
    purpose_code: PurposeCode
    tenant_id: str = LOCAL_DEVELOPMENT_TENANT


def seed_authorization_purposes(session: Session) -> None:
    """Insert the declared purposes used by this slice."""
    for code in PurposeCode:
        if session.get(AuthorizationPurpose, code.value) is not None:
            continue
        session.add(
            AuthorizationPurpose(
                purpose_code=code.value,
                purpose_label=purpose_label(code),
                purpose_description=purpose_label(code),
            )
        )


def purpose_label(code: PurposeCode) -> str:
    """Return the officer-facing label for a purpose code."""
    match code:
        case PurposeCode.COVERAGE_REVIEW:
            return "Review control coverage"
        case PurposeCode.COMPLIANCE_GOVERNANCE:
            return "Govern obligations and applicability"
        case PurposeCode.EVIDENCE_BINDING:
            return "Attach or bind evidence"
        case PurposeCode.EVIDENCE_RETENTION:
            return "Manage evidence retention and legal hold"
        case PurposeCode.HEALTH_PROBE:
            return "Probe service health"
        case PurposeCode.POLICY_AUTHORING:
            return "Author or revise a policy"
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def require_purpose(
    actor_identifier: str | None,
    purpose_value: str | None,
    required: PurposeCode,
    *,
    tenant_id: str = LOCAL_DEVELOPMENT_TENANT,
) -> AuthorizationDecision:
    """Accept only a named actor, exact tenant, and required declared purpose."""
    if not actor_identifier or not purpose_value:
        raise HTTPException(
            status_code=401,
            detail="State the actor and purpose before touching evidence.",
        )
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Resolve the tenant before this action.")
    try:
        purpose_code = PurposeCode(purpose_value)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="That purpose is not authorized.") from exc
    if purpose_code is not required:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires {required.value}.",
        )
    return AuthorizationDecision(actor_identifier, purpose_code, tenant_id)
