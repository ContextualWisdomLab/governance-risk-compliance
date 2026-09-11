"""RED contracts for deriving protected-route identity from Keyverse bearer tokens."""

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


NOW = datetime(2026, 8, 19, 12, 30, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
ROLE = "compliance_officer"
ACTOR_ID = "keyverse-officer-1"


def _material() -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and its reviewed public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "route-key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _verifier(public_jwk: dict[str, Any]) -> KeyverseAccessTokenVerifier:
    """Build the deterministic Keyverse verifier used by protected-route tests."""
    key_set = parse_keyverse_jwks(json.dumps({"keys": [public_jwk]}).encode())
    settings = KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({ROLE}),
        clock_skew_seconds=60,
    )
    return KeyverseAccessTokenVerifier(settings, key_set, now=lambda: NOW)


def _token(private_key: Any, *, scope: str) -> str:
    """Sign one otherwise-valid human access token for the requested scope."""
    claims = {
        "iss": ISSUER,
        "sub": ACTOR_ID,
        "aud": AUDIENCE,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
        "iat": int((NOW - timedelta(seconds=1)).timestamp()),
        "jti": "route-token-1",
        "client_id": CLIENT_ID,
        "scope": scope,
        "role": ROLE,
        "org": "tenant-1",
        "workspace": "workspace-1",
        "principal_kind": "human",
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "route-key-1"},
    )


def _client(verifier: KeyverseAccessTokenVerifier) -> TestClient:
    """Return one isolated local-preview client with Keyverse route auth enabled."""
    return TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=verifier,
        )
    )


def test_verified_bearer_subject_overrides_spoofed_actor_header() -> None:
    """A protected mutation records the signed subject, never caller identity headers."""
    private_key, public_jwk = _material()
    response = _client(_verifier(public_jwk)).post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.write')}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "evidence_binding",
        },
        json={
            "evidence_title": "CSAP access approval register",
            "payload_text": "Officer Kim approved access for user@example.go.kr.",
        },
    )

    assert response.status_code == 201
    assert response.json()["collector_actor"] == ACTOR_ID


def test_identity_header_cannot_replace_missing_bearer_token() -> None:
    """Spoofable identity headers cannot authenticate a Keyverse-protected route."""
    _private_key, public_jwk = _material()
    response = _client(_verifier(public_jwk)).post(
        "/evidence-records",
        headers={
            "X-Actor-Id": ACTOR_ID,
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Denied", "payload_text": "Denied"},
    )

    assert response.status_code == 401


def test_malformed_authorization_header_fails_closed() -> None:
    """A non-Bearer authorization scheme cannot reach the protected mutation."""
    _private_key, public_jwk = _material()
    response = _client(_verifier(public_jwk)).post(
        "/evidence-records",
        headers={
            "Authorization": "Basic opaque-credential",
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Denied", "payload_text": "Denied"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Present one Keyverse bearer token before this action."


def test_invalid_bearer_token_fails_closed_as_unauthenticated() -> None:
    """A syntactically present but unverifiable bearer token is rejected as invalid."""
    _private_key, public_jwk = _material()
    response = _client(_verifier(public_jwk)).post(
        "/evidence-records",
        headers={
            "Authorization": "Bearer not-a-jwt",
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Denied", "payload_text": "Denied"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "The Keyverse bearer token is invalid."


def test_verified_bearer_requires_action_scope_before_mutation() -> None:
    """A valid Keyverse identity without the action scope cannot mutate evidence."""
    private_key, public_jwk = _material()
    response = _client(_verifier(public_jwk)).post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.policy.read')}",
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Denied", "payload_text": "Denied"},
    )

    assert response.status_code == 403


def test_coverage_reads_require_verified_identity_when_keyverse_is_enabled() -> None:
    """Coverage reads use the signed tenant instead of the local fallback tenant."""
    private_key, public_jwk = _material()
    client = _client(_verifier(public_jwk))
    denied = client.get(
        "/controls",
        headers={"X-Purpose": "coverage_review"},
    )
    assert denied.status_code == 401
    allowed = client.get(
        "/controls",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.control.read')}",
            "X-Purpose": "coverage_review",
        },
    )
    assert allowed.status_code == 200


def test_legal_hold_requires_verified_retention_scope() -> None:
    """Legal-hold changes require the signed retention scope, not evidence-write scope."""
    private_key, public_jwk = _material()
    client = _client(_verifier(public_jwk))
    created = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.write')}",
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Retention evidence", "payload_text": "Exact evidence."},
    )
    assert created.status_code == 201
    record_id = created.json()["evidence_record_id"]

    denied = client.post(
        f"/evidence-records/{record_id}/legal-hold",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.write')}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "evidence_retention",
        },
        json={"hold_reason": "Active audit", "hold_authority": "audit-2026-08"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/evidence-records/{record_id}/legal-hold",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='grc.evidence.retention')}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "evidence_retention",
        },
        json={"hold_reason": "Active audit", "hold_authority": "audit-2026-08"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["legal_hold_active"] is True
