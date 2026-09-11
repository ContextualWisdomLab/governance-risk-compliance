"""Protect evidence-derived coverage state behind the Keyverse tenant boundary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cwl_grc.app import create_app
from cwl_grc.catalog import FrameworkCode
from cwl_grc.keyverse_authentication import (
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)


NOW = datetime(2026, 9, 12, 1, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"


def _signing_material() -> tuple[Any, dict[str, Any]]:
    """Return one RSA signing key and its reviewed public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-coverage", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _verifier(jwk: dict[str, Any]) -> KeyverseAccessTokenVerifier:
    """Build the closed resource-server verifier used by this regression."""
    settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({"compliance_officer"}),
        clock_skew_seconds=60,
    )
    return KeyverseAccessTokenVerifier(
        settings,
        parse_keyverse_jwks(json.dumps({"keys": [jwk]}).encode()),
        now=lambda: NOW,
    )


def _token(
    private_key: Any,
    *,
    tenant: str,
    jti: str,
    scope: str = "openid grc.policy.read grc.policy.write grc.evidence.write",
) -> str:
    """Sign one human officer token for a named Keyverse tenant."""
    claims = {
        "iss": ISSUER,
        "sub": "officer-park",
        "aud": AUDIENCE,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((NOW - timedelta(seconds=5)).timestamp()),
        "iat": int((NOW - timedelta(seconds=5)).timestamp()),
        "jti": jti,
        "client_id": CLIENT_ID,
        "scope": scope,
        "role": "compliance_officer",
        "org": tenant,
        "workspace": "grc-primary",
        "principal_kind": "human",
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-coverage", "typ": "at+jwt"},
    )


def _catalog_ids(response) -> set[str]:  # noqa: ANN001
    """Return catalog identifiers from one uncovered-controls response."""
    return {item["catalog_identifier"] for item in response.json()["controls"]}


def test_uncovered_controls_are_authenticated_and_tenant_scoped() -> None:
    """One tenant's evidence must neither hide nor disclose another tenant's coverage gap."""
    private_key, jwk = _signing_material()
    client = TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=_verifier(jwk),
        )
    )
    acme_token = _token(private_key, tenant="tenant-acme", jti="coverage-acme")
    other_token = _token(private_key, tenant="tenant-other", jti="coverage-other")
    coverage_params = {"framework": FrameworkCode.CSAP_2026.value}

    anonymous = client.get("/controls/uncovered", params=coverage_params)
    assert anonymous.status_code == 401

    evidence = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {acme_token}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "evidence_title": "Acme CSAP 10.2.1 access register",
            "payload_text": "Acme reviewed unique-user access grants.",
        },
    )
    assert evidence.status_code == 201
    bound = client.post(
        "/control-evidence-bindings",
        headers={
            "Authorization": f"Bearer {acme_token}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "10.2.1",
            "evidence_record_id": evidence.json()["evidence_record_id"],
        },
    )
    assert bound.status_code == 201

    acme_coverage = client.get(
        "/controls/uncovered",
        params=coverage_params,
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert acme_coverage.status_code == 200
    assert "10.2.1" not in _catalog_ids(acme_coverage)

    other_coverage = client.get(
        "/controls/uncovered",
        params=coverage_params,
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_coverage.status_code == 200
    assert "10.2.1" in _catalog_ids(other_coverage)

    insufficient_scope = _token(
        private_key,
        tenant="tenant-other",
        jti="coverage-no-read",
        scope="openid grc.evidence.write",
    )
    denied = client.get(
        "/controls/uncovered",
        params=coverage_params,
        headers={"Authorization": f"Bearer {insufficient_scope}"},
    )
    assert denied.status_code == 403
