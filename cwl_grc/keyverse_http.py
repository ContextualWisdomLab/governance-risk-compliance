"""Bind Keyverse access tokens onto GRC HTTP routes without trusting actor headers."""

from __future__ import annotations

import os
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
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
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)
from cwl_grc.remote_access import keyverse_start_is_required

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


def cli_bearer_authorization() -> str | None:
    """Return a Bearer header from ``CWL_GRC_ACCESS_TOKEN`` without copying it elsewhere."""
    token = os.environ.get("CWL_GRC_ACCESS_TOKEN", "").strip()
    if not token:
        return None
    return f"Bearer {token}"


def authenticate_cli_principal(
    *,
    declared_actor: str | None,
    required_scopes: Collection[str],
) -> RequestPrincipal:
    """Resolve the CLI actor from Keyverse when required, else from ``--actor``.

    ``--actor`` is not identity under ``CWL_GRC_REQUIRE_KEYVERSE``. A matching
    value is tolerated; a mismatch is impersonation and fails closed.
    """
    return authenticate_keyverse_request(
        process_access_token_verifier(),
        authorization=cli_bearer_authorization(),
        declared_actor=declared_actor,
        required_scopes=required_scopes,
    )


def process_access_token_verifier() -> KeyverseAccessTokenVerifier | None:
    """Load a reviewed offline JWKS verifier when a hardened start is required."""
    if not keyverse_start_is_required():
        return None
    issuer = os.environ.get("CWL_GRC_KEYVERSE_ISSUER", "").strip()
    audience = os.environ.get("CWL_GRC_KEYVERSE_AUDIENCE", "").strip()
    jwks_path = os.environ.get("CWL_GRC_KEYVERSE_JWKS_PATH", "").strip()
    clients = _csv_identifiers(os.environ.get("CWL_GRC_KEYVERSE_CLIENT_IDS", ""))
    roles = _csv_identifiers(
        os.environ.get("CWL_GRC_KEYVERSE_ROLES", "compliance_officer")
    )
    if not issuer or not audience or not jwks_path or not clients or not roles:
        raise ValueError(
            "A reviewed Keyverse issuer, audience, client set, role set, and JWKS "
            "path are required when CWL_GRC_REQUIRE_KEYVERSE is set."
        )
    path = Path(jwks_path)
    if not path.is_file():
        raise ValueError("The Keyverse JWKS path must be a readable file.")
    document = path.read_bytes()
    try:
        return KeyverseAccessTokenVerifier(
            KeyverseAccessTokenSettings(
                issuer=issuer,
                audience=audience,
                allowed_client_ids=clients,
                allowed_roles=roles,
            ),
            parse_keyverse_jwks(document),
        )
    except AccessTokenValidationError as exc:
        raise ValueError(str(exc)) from exc


def _csv_identifiers(raw: str) -> frozenset[str]:
    """Split a comma-separated identifier list and drop empty fragments."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class RequestPrincipal:
    """Actor and tenant resolved for one HTTP or local-preview action."""

    actor_identifier: str
    tenant_identifier: str
    issuer_identifier: str = LOCAL_PREVIEW_ISSUER
    client_identifier: str = LOCAL_PREVIEW_CLIENT


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
        status = 403 if isinstance(exc, AccessTokenScopeError) else 401
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    _reject_impersonation(principal, declared_actor, declared_tenant)
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
