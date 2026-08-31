"""Bind Keyverse access tokens onto GRC HTTP routes without trusting actor headers."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from cwl_grc.authorization import (
    AuthorizationDecision,
    LOCAL_PREVIEW_CLIENT,
    LOCAL_PREVIEW_ISSUER,
    LOCAL_PREVIEW_TENANT,
    PurposeCode,
    require_purpose,
)
from cwl_grc.correlation import current_correlation_reference
from cwl_grc.keyverse_authentication import (
    AccessTokenScopeError,
    AccessTokenValidationError,
    AuthenticatedPrincipal,
    KeyverseAccessTokenVerifier,
)

POLICY_READ_SCOPES = ("grc.policy.read",)
POLICY_WRITE_SCOPES = ("grc.policy.write",)
EVIDENCE_WRITE_SCOPES = ("grc.evidence.write",)
KEYVERSE_BEARER_SCHEME = "KeyverseBearer"
MAX_PERSISTED_IDENTITY_LENGTH = 128
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
            f"evidence writes need {EVIDENCE_WRITE_SCOPES[0]}. Catalog, /healthz, "
            "and the data-free officer bootstrap at / remain public. Protected "
            "officer state is loaded only through Bearer-authorized APIs. Local "
            "preview without a verifier still accepts declared actor headers and "
            "is not a production deployment."
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
    issuer_identifier: str = LOCAL_PREVIEW_ISSUER
    client_identifier: str = LOCAL_PREVIEW_CLIENT


def extract_bearer_token(authorization: str | None) -> str:
    """Return one compact token while matching the HTTP auth scheme case-insensitively."""
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Present a Keyverse access token before this action.",
        )
    scheme, separator, token = authorization.partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not token
        or token != token.strip()
        or any(character.isspace() for character in token)
    ):
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
    """Return the verified actor and tenant, or the fixed local-preview tenant.

    When a verifier is configured, ``X-Actor-Id`` is not identity. A matching
    header is tolerated; a mismatched header is impersonation and fails closed.
    """
    if verifier is None:
        if not declared_actor:
            raise HTTPException(
                status_code=401,
                detail="State the actor and purpose before touching evidence.",
            )
        return RequestPrincipal(declared_actor, LOCAL_PREVIEW_TENANT)
    try:
        principal = verifier.verify(
            extract_bearer_token(authorization),
            required_scopes=required_scopes,
        )
    except AccessTokenValidationError as exc:
        status = 403 if isinstance(exc, AccessTokenScopeError) else 401
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    _reject_impersonation(principal, declared_actor, declared_tenant)
    _reject_impersonation(principal, declared_actor, declared_tenant)
    _reject_unpersistable_identity(principal)
    return RequestPrincipal(
        principal.actor_id,
        principal.tenant_id,
        issuer_identifier=verifier.issuer,
        client_identifier=principal.client_id,
    )


def decision_for_request(
    principal: RequestPrincipal,
    purpose_value: str | None,
    required: PurposeCode,
) -> AuthorizationDecision:
    """Build an attributed purpose decision for one authenticated request."""
    return require_purpose(
        principal.actor_identifier,
        purpose_value,
        required,
        tenant_identifier=principal.tenant_identifier,
        issuer_identifier=principal.issuer_identifier,
        client_identifier=principal.client_identifier,
        correlation_reference=current_correlation_reference(),
    )


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


def _reject_unpersistable_identity(principal: AuthenticatedPrincipal) -> None:
    """Reject verified identities that exceed the GRC-owned persistence contract."""
    if (
        len(principal.actor_id) > MAX_PERSISTED_IDENTITY_LENGTH
        or len(principal.tenant_id) > MAX_PERSISTED_IDENTITY_LENGTH
    ):
        raise HTTPException(
            status_code=401,
            detail="The verified Keyverse identity exceeds the GRC persistence boundary.",
        )
