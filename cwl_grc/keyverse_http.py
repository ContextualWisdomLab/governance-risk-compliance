"""Bind Keyverse access tokens onto GRC HTTP routes without trusting actor headers."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

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
KEYVERSE_BEARER_SCHEME = "KeyverseBearer"
KEYVERSE_PROTECTED_OPERATIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("/policy-documents", "post", POLICY_WRITE_SCOPES),
    (
        "/policy-documents/{policy_document_id}/versions",
        "post",
        POLICY_WRITE_SCOPES,
    ),
    ("/policy-documents", "get", POLICY_READ_SCOPES),
    ("/policy-gaps", "get", POLICY_READ_SCOPES),
    ("/evidence-records", "post", EVIDENCE_WRITE_SCOPES),
    ("/control-evidence-bindings", "post", EVIDENCE_WRITE_SCOPES),
    ("/", "get", POLICY_READ_SCOPES),
    ("/officer/policy", "post", POLICY_WRITE_SCOPES),
    ("/officer/evidence", "post", EVIDENCE_WRITE_SCOPES),
)


def keyverse_bearer_security_scheme() -> dict[str, Any]:
    """Describe the RFC 9068 Keyverse access-token contract for OpenAPI consumers."""
    return {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "at+jwt",
        "description": (
            "Keyverse RFC 9068 access token. Officer policy reads need "
            f"{POLICY_READ_SCOPES[0]}; policy writes need {POLICY_WRITE_SCOPES[0]}; "
            f"evidence writes need {EVIDENCE_WRITE_SCOPES[0]}. Catalog and "
            "/healthz remain public. Local preview without a verifier still "
            "accepts declared actor headers and is not a production deployment."
        ),
    }


def apply_keyverse_openapi_security(schema: dict[str, Any]) -> dict[str, Any]:
    """Attach Keyverse Bearer security to officer policy and evidence operations."""
    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes[KEYVERSE_BEARER_SCHEME] = keyverse_bearer_security_scheme()
    paths = schema.setdefault("paths", {})
    for path, method, scopes in KEYVERSE_PROTECTED_OPERATIONS:
        operation = paths[path][method]
        operation["security"] = [{KEYVERSE_BEARER_SCHEME: list(scopes)}]
    return schema


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
