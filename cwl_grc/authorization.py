"""Purpose-limited authorization for policy and evidence work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing import assert_never

from fastapi import HTTPException
from sqlalchemy.orm import Session

from cwl_grc.models import AuthorizationPurpose


class PurposeCode(StrEnum):
    """Declared purposes that may touch GRC records."""

    COVERAGE_REVIEW = "coverage_review"
    EVIDENCE_BINDING = "evidence_binding"
    HEALTH_PROBE = "health_probe"
    POLICY_AUTHORING = "policy_authoring"


@dataclass(frozen=True)
class AuthorizationDecision:
    """An actor acting under one declared purpose."""

    actor_identifier: str
    purpose_code: PurposeCode


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
        case PurposeCode.EVIDENCE_BINDING:
            return "Attach or bind evidence"
        case PurposeCode.HEALTH_PROBE:
            return "Probe service health"
        case PurposeCode.POLICY_AUTHORING:
            return "Author or revise a policy"
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def require_declared_tenant(tenant_identifier: str | None) -> str:
    """Accept a declared tenant label for local preview scoping."""
    tenant = (tenant_identifier or "").strip()
    if not tenant:
        raise HTTPException(
            status_code=401,
            detail="Declare the tenant before reviewing workspace posture.",
        )
    return tenant


def require_purpose(
    actor_identifier: str | None,
    purpose_value: str | None,
    required: PurposeCode,
) -> AuthorizationDecision:
    """Accept only a named actor acting under the required purpose."""
    if not actor_identifier or not purpose_value:
        raise HTTPException(
            status_code=401,
            detail="State the actor and purpose before touching evidence.",
        )
    try:
        purpose_code = PurposeCode(purpose_value)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="That purpose is not authorized.") from exc
    if purpose_code is not required:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires {required.value}.",
        )
    return AuthorizationDecision(actor_identifier, purpose_code)
