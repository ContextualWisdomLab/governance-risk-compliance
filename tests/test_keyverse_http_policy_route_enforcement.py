"""RED contracts for Keyverse authorization on policy HTTP mutations."""

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


NOW = datetime(2026, 8, 19, 13, 30, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
ROLE = "compliance_officer"


def _material() -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and matching public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "policy-key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _client(public_jwk: dict[str, Any]) -> TestClient:
    """Create an isolated Keyverse-enabled local GRC application."""
    key_set = parse_keyverse_jwks(json.dumps({"keys": [public_jwk]}).encode())
    settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({ROLE}),
    )
    verifier = KeyverseAccessTokenVerifier(settings, key_set, now=lambda: NOW)
    return TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=verifier,
        )
    )


def _token(private_key: Any, *, scope: str) -> str:
    """Sign one exact human access token with the supplied scope string."""
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": "keyverse-policy-officer-1",
            "aud": AUDIENCE,
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
            "iat": int((NOW - timedelta(seconds=1)).timestamp()),
            "jti": "policy-route-token-1",
            "client_id": CLIENT_ID,
            "scope": scope,
            "role": ROLE,
            "org": "tenant-1",
            "workspace": "workspace-1",
            "principal_kind": "human",
        },
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "policy-key-1"},
    )


def _policy_body() -> dict[str, Any]:
    """Return one valid policy command payload without optional control mappings."""
    return {
        "policy_title": "Access review policy",
        "policy_body": "Review privileged access every quarter.",
        "control_refs": [],
    }


def test_policy_creation_requires_keyverse_bearer_when_verifier_is_enabled() -> None:
    """Legacy identity headers cannot replace a bearer token on policy authoring."""
    _private_key, public_jwk = _material()
    response = _client(public_jwk).post(
        "/policy-documents",
        headers={
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "policy_authoring",
        },
        json=_policy_body(),
    )
    assert response.status_code == 401


def test_policy_creation_requires_policy_write_scope() -> None:
    """A valid principal without policy-write scope cannot author a policy."""
    private_key, public_jwk = _material()
    response = _client(public_jwk).post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.policy.read')}",
            "X-Purpose": "policy_authoring",
        },
        json=_policy_body(),
    )
    assert response.status_code == 403


def test_policy_create_and_revision_accept_verified_policy_writer() -> None:
    """A verified policy writer can create and append an immutable policy edition."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    headers = {
        "Authorization": f"Bearer {_token(private_key, scope='grc.policy.write')}",
        "X-Actor-Id": "spoofed-officer",
        "X-Purpose": "policy_authoring",
    }
    created = client.post("/policy-documents", headers=headers, json=_policy_body())
    assert created.status_code == 201

    policy_document_id = created.json()["policy_document_id"]
    revised = client.post(
        f"/policy-documents/{policy_document_id}/versions",
        headers=headers,
        json={
            "policy_body": "Review privileged access monthly.",
            "control_refs": [],
        },
    )
    assert revised.status_code == 201
    assert revised.json()["current_version"]["version_number"] == 2


def test_officer_policy_form_requires_keyverse_bearer_when_verifier_is_enabled() -> None:
    """The browser mutation cannot bypass Keyverse with a submitted actor field."""
    _private_key, public_jwk = _material()
    response = _client(public_jwk).post(
        "/officer/policy",
        data={
            "policy_title": "Denied policy",
            "policy_body": "The submitted actor is not authentication.",
            "actor_identifier": "spoofed-officer",
        },
    )
    assert response.status_code == 401
