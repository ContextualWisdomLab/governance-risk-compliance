"""Bind Keyverse access tokens onto GRC HTTP routes without trusting actor headers."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from fastapi import HTTPException

from cwl_grc.authorization import LOCAL_PREVIEW_TENANT
from cwl_grc.keyverse_authentication import (
    AccessTokenValidationError,
    AuthenticatedPrincipal,
    KeyverseAccessTokenVerifier,
)

POLICY_READ_SCOPES = ("grc.policy.read",)
POLICY_WRITE_SCOPES = ("grc.policy.write",)
EVIDENCE_WRITE_SCOPES = ("grc.evidence.write",)


@dataclass(frozen=True)
class RequestPrincipal:
    """Actor and tenant resolved for one HTTP or local-preview action."""

    actor_identifier: str
    tenant_identifier: str


def extract_bearer_token(authorization: str | None) -> str:
    """Return the compact access token from a Bearer authorization header."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Present a Keyverse access token before this action.",
        )
    token = authorization[7:].strip()
    if not token or token != authorization[7:] or " " in token:
        raise HTTPException(
            status_code=401,
            detail="Present a Keyverse access token before this action.",
        )
    return token


def authenticate_keyverse_request(
    verifier: KeyverseAccessTokenVerifier | None,
    *,
    authorization: str | None,
    declared_actor: str | None,
    declared_tenant: str | None = None,
    required_scopes: Collection[str] = (),
) -> RequestPrincipal:
    """Return the verified actor and tenant, or local-preview declarations.

    When a verifier is configured, ``X-Actor-Id`` is not identity. A matching
    header is tolerated; a mismatched header is impersonation and fails closed.
    """
    if verifier is None:
        if not declared_actor:
            raise HTTPException(
                status_code=401,
                detail="State the actor and purpose before touching evidence.",
            )
        tenant = (declared_tenant or "").strip() or LOCAL_PREVIEW_TENANT
        return RequestPrincipal(declared_actor, tenant)
    try:
        principal = verifier.verify(
            extract_bearer_token(authorization),
            required_scopes=required_scopes,
        )
    except AccessTokenValidationError as exc:
        status = 403 if "required scope" in str(exc) else 401
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    _reject_impersonation(principal, declared_actor, declared_tenant)
    return RequestPrincipal(principal.actor_id, principal.tenant_id)


def _reject_impersonation(
    principal: AuthenticatedPrincipal,
    declared_actor: str | None,
    declared_tenant: str | None,
) -> None:
    """Reject caller headers that contradict the verified Keyverse principal."""
    if declared_actor and declared_actor != principal.actor_id:
        raise HTTPException(
            status_code=401,
            detail="The actor header cannot impersonate a Keyverse subject.",
        )
    if declared_tenant and declared_tenant != principal.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="The tenant header does not match the Keyverse organization.",
        )
