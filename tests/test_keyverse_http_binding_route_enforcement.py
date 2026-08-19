"""RED contracts for Keyverse authorization on evidence-binding HTTP mutations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.keyverse_authentication import (
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)


NOW = datetime(2026, 8, 19, 13, 45, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
ROLE = "compliance_officer"
SOC2_FRAMEWORK = "soc2_tsc_2017"


def _material() -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and matching public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "binding-key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _client(public_jwk: dict[str, Any]) -> TestClient:
    """Create one isolated Keyverse-enabled GRC app."""
    key_set = parse_keyverse_jwks(json.dumps({"keys": [public_jwk]}).encode())
    settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({ROLE}),
    )
    return TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=KeyverseAccessTokenVerifier(
                settings,
                key_set,
                now=lambda: NOW,
            ),
        )
    )


def _token(private_key: Any, *, scope: str) -> str:
    """Sign one exact human access token with requested scopes."""
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": "keyverse-evidence-officer-1",
            "aud": AUDIENCE,
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
            "iat": int((NOW - timedelta(seconds=1)).timestamp()),
            "jti": "binding-token-1",
            "client_id": CLIENT_ID,
            "scope": scope,
            "role": ROLE,
            "org": "tenant-1",
            "workspace": "workspace-1",
            "principal_kind": "human",
        },
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "binding-key-1"},
    )


def _create_evidence(client: TestClient, private_key: Any) -> str:
    """Create one evidence record through the already-protected evidence route."""
    response = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.write')}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "evidence_title": "Quarterly access review",
            "payload_text": "Reviewed on 2026-08-19.",
        },
    )
    assert response.status_code == 201
    return str(response.json()["evidence_record_id"])


def test_binding_route_rejects_identity_header_without_bearer() -> None:
    """Caller-supplied actor headers cannot authorize a control binding."""
    _private_key, public_jwk = _material()
    response = _client(public_jwk).post(
        "/control-evidence-bindings",
        headers={
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "evidence_binding",
        },
        json={
            "framework": SOC2_FRAMEWORK,
            "catalog_identifier": "CC1.1",
            "evidence_record_id": "not-reached",
        },
    )
    assert response.status_code == 401


def test_binding_route_requires_evidence_write_scope() -> None:
    """A verified principal without evidence-write scope cannot bind evidence."""
    private_key, public_jwk = _material()
    response = _client(public_jwk).post(
        "/control-evidence-bindings",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.policy.read')}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "framework": SOC2_FRAMEWORK,
            "catalog_identifier": "CC1.1",
            "evidence_record_id": "not-reached",
        },
    )
    assert response.status_code == 403


def test_verified_evidence_writer_can_bind_existing_evidence() -> None:
    """A verified evidence writer can bind exact stored evidence to a catalog control."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    evidence_record_id = _create_evidence(client, private_key)
    response = client.post(
        "/control-evidence-bindings",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.write')}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "evidence_binding",
        },
        json={
            "framework": SOC2_FRAMEWORK,
            "catalog_identifier": "CC1.1",
            "evidence_record_id": evidence_record_id,
        },
    )
    assert response.status_code == 201
    assert response.json()["evidence_record_id"] == evidence_record_id
