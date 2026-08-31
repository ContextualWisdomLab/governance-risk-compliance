"""Officer home forms send Keyverse Bearer tokens and purpose headers."""

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


NOW = datetime(2026, 8, 23, 4, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"


def _signing_material(kid: str) -> tuple[Any, dict[str, Any]]:
    """Return one RSA key pair as a public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _settings() -> KeyverseAccessTokenSettings:
    """Return the closed GRC resource-server policy."""
    return KeyverseAccessTokenSettings(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_client_ids=frozenset({CLIENT_ID}),
        allowed_roles=frozenset({"compliance_officer"}),
        clock_skew_seconds=60,
    )


def _claims(**overrides: Any) -> dict[str, Any]:
    """Return one RFC 9068-compatible human access-token claim set."""
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "officer-park",
        "aud": AUDIENCE,
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((NOW - timedelta(seconds=5)).timestamp()),
        "iat": int((NOW - timedelta(seconds=5)).timestamp()),
        "jti": "token-park-01",
        "client_id": CLIENT_ID,
        "scope": "openid grc.policy.read grc.policy.write grc.evidence.write",
        "role": "compliance_officer",
        "org": "tenant-acme",
        "workspace": "grc-primary",
        "principal_kind": "human",
    }
    claims.update(overrides)
    return claims


def _token(private_key: Any, **claim_overrides: Any) -> str:
    """Sign one access token for the GRC resource audience."""
    return jwt.encode(
        _claims(**claim_overrides),
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1", "typ": "at+jwt"},
    )


def _client(verifier: KeyverseAccessTokenVerifier | None = None) -> TestClient:
    """Return an isolated app client, optionally with Keyverse verification."""
    return TestClient(
        create_app(
            database_url="sqlite://",
            evidence_key=None,
            access_token_verifier=verifier,
        )
    )


def _verifier(jwk: dict[str, Any]) -> KeyverseAccessTokenVerifier:
    """Build a verifier from one reviewed public key."""
    return KeyverseAccessTokenVerifier(
        _settings(),
        parse_keyverse_jwks(json.dumps({"keys": [jwk]}).encode()),
        now=lambda: NOW,
    )


def test_officer_home_forms_send_keyverse_bearer_and_purpose() -> None:
    """Officer home posts Bearer plus purpose and keeps actor as token claims."""
    private_key, jwk = _signing_material("key-1")
    client = _client(_verifier(jwk))
    token = _token(private_key)
    home = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert home.status_code == 200
    assert 'id="keyverse-access-token"' in home.text
    assert 'type="password"' in home.text
    assert "sessionStorage" in home.text
    assert "policy_authoring" in home.text
    assert "evidence_binding" in home.text
    assert "fetch(form.action" in home.text
    script = home.text.split("<script>")[1]
    assert 'headers.Authorization = "Bearer " + token' in script
    assert 'headers["X-Actor-Id"] = actor' in script
    assert "console.log" not in home.text

    spoofed = client.post(
        "/officer/policy",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "policy_authoring",
        },
        data={
            "policy_title": "Spoofed Form Policy",
            "policy_body": "Form actor must not become identity.",
            "actor_identifier": "spoofed-officer",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
        follow_redirects=False,
    )
    assert spoofed.status_code == 401
    assert "impersonate" in spoofed.json()["detail"]

    authored = client.post(
        "/officer/policy",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "policy_authoring",
        },
        data={
            "policy_title": "Park Officer Home Policy",
            "policy_body": "Bearer subject authors this policy.",
            "actor_identifier": "spoofed-officer",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
        follow_redirects=False,
    )
    assert authored.status_code == 303

    listed = client.get("/policy-documents", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    titles = [item["policy_title"] for item in listed.json()["policies"]]
    assert titles == ["Park Officer Home Policy"]
    other = _token(private_key, sub="officer-kim", jti="token-kim-form")
    hidden = client.get("/policy-documents", headers={"Authorization": f"Bearer {other}"})
    assert hidden.json()["policies"] == []

    wrong_purpose = client.post(
        "/officer/evidence",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "policy_authoring",
        },
        data={
            "evidence_title": "CSAP 10.2.1 access-grant register",
            "payload_text": "Officer Park (park@example.co.kr) approved unique user IDs.",
            "control_ref": f"{FrameworkCode.CSAP_2026.value}|10.2.1",
        },
        follow_redirects=False,
    )
    assert wrong_purpose.status_code == 403

    evidence = client.post(
        "/officer/evidence",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "evidence_binding",
        },
        data={
            "evidence_title": "CSAP 10.2.1 access-grant register",
            "payload_text": "Officer Park (park@example.co.kr) approved unique user IDs.",
            "control_ref": f"{FrameworkCode.CSAP_2026.value}|10.2.1",
        },
        follow_redirects=False,
    )
    assert evidence.status_code == 303
    follow = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert follow.status_code == 200
    records = client.get("/policy-gaps", headers={"Authorization": f"Bearer {token}"})
    assert records.status_code == 200
    assert records.json()["gaps"] == []


def test_local_preview_officer_forms_send_declared_actor_without_bearer() -> None:
    """Local preview browser posts use X-Actor-Id when no Keyverse token is present."""
    client = _client()
    authored = client.post(
        "/officer/policy",
        headers={"X-Actor-Id": "officer-ahn", "X-Purpose": "policy_authoring"},
        data={
            "policy_title": "Local Preview Officer Policy",
            "policy_body": "Declared actor is identity only when Keyverse is off.",
            "actor_identifier": "officer-ahn",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
        follow_redirects=False,
    )
    assert authored.status_code == 303
    missing = client.post(
        "/officer/evidence",
        data={
            "control_ref": "not-a-ref",
            "evidence_title": "Must authenticate first",
            "payload_text": "ahn@example.co.kr",
        },
    )
    assert missing.status_code == 401
    dummy_bearer = client.post(
        "/officer/policy",
        headers={"Authorization": "Bearer unused-local-preview", "X-Purpose": "policy_authoring"},
        data={
            "policy_title": "Token without actor",
            "policy_body": "Local preview ignores Bearer and needs a declared actor.",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
    )
    assert dummy_bearer.status_code == 401


def test_keyverse_home_bootstraps_without_disclosing_officer_policy_state() -> None:
    """Browser navigation loads only a shell until Keyverse authorizes the gap query."""
    private_key, jwk = _signing_material("key-1")
    client = _client(_verifier(jwk))
    token = _token(private_key)
    authored = client.post(
        "/officer/policy",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "policy_authoring",
        },
        data={
            "policy_title": "Browser Bootstrap Policy",
            "policy_body": "Protected policy state must not be server-rendered before auth.",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
        follow_redirects=False,
    )
    assert authored.status_code == 303

    bootstrap = client.get("/")
    assert bootstrap.status_code == 200
    assert 'data-keyverse-required="true"' in bootstrap.text
    assert 'id="load-keyverse-policy-gaps"' in bootstrap.text
    assert 'id="policy-gap-list"' in bootstrap.text
    assert 'id="officer-evidence-control"' in bootstrap.text
    assert 'fetch("/policy-gaps"' in bootstrap.text
    assert "Browser Bootstrap Policy" not in bootstrap.text
    assert "Load my policy gaps" in bootstrap.text

    protected = client.get("/policy-gaps")
    assert protected.status_code == 401
