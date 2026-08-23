"""Officer HTTP routes consume Keyverse access tokens instead of actor headers."""

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
    AccessTokenScopeError,
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


def test_keyverse_bearer_token_authors_policy_and_hides_other_officers() -> None:
    """A verified officer authors under the token subject, not a spoofed header."""
    private_key, jwk = _signing_material("key-1")
    verifier = _verifier(jwk)
    client = _client(verifier)
    token = _token(private_key)

    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Actor-Id": "spoofed-officer",
            "X-Purpose": "policy_authoring",
        },
        json={
            "policy_title": "Logical Access Policy",
            "policy_body": "Least privilege for CSAP 10.2.1.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 401
    assert "impersonate" in created.json()["detail"]

    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Purpose": "policy_authoring",
        },
        json={
            "policy_title": "Logical Access Policy",
            "policy_body": "Least privilege for CSAP 10.2.1.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 201
    assert created.json()["policy_title"] == "Logical Access Policy"

    listed = client.get(
        "/policy-documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert listed.json()["next_action"].startswith("Review policy gaps")
    assert len(listed.json()["policies"]) == 1

    other = _token(private_key, sub="officer-kim", jti="token-kim-01")
    other_list = client.get(
        "/policy-documents",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert other_list.json()["policies"] == []
    other_gaps = client.get(
        "/policy-gaps",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert other_gaps.json()["gaps"] == []


def test_keyverse_route_rejects_missing_token_wrong_tenant_and_missing_scope() -> None:
    """Protected routes fail closed until a matching Keyverse token is presented."""
    private_key, jwk = _signing_material("key-1")
    client = _client(_verifier(jwk))

    missing = client.post(
        "/policy-documents",
        headers={"X-Actor-Id": "officer-park", "X-Purpose": "policy_authoring"},
        json={"policy_title": "X", "policy_body": "Y", "control_refs": []},
    )
    assert missing.status_code == 401

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "cwl-grc"}

    tenant = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key)}",
            "X-Purpose": "evidence_binding",
            "X-Tenant-Id": "tenant-other",
        },
        json={"evidence_title": "Register", "payload_text": "Exact officer note."},
    )
    assert tenant.status_code == 403

    scoped = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {_token(private_key, scope='openid grc.policy.read')}",
            "X-Purpose": "evidence_binding",
        },
        json={"evidence_title": "Register", "payload_text": "Exact officer note."},
    )
    assert scoped.status_code == 403


def test_missing_scope_is_forbidden_by_exception_type_not_message_text() -> None:
    """Insufficient scope is 403 because the token is authentic, not because of wording."""
    from fastapi import HTTPException

    from cwl_grc.keyverse_http import authenticate_keyverse_request

    class _ScopeVerifier:
        def verify(self, token: str, *, required_scopes=()):  # noqa: ANN001
            raise AccessTokenScopeError(
                "token is authentic but this action is not granted"
            )

    try:
        authenticate_keyverse_request(
            _ScopeVerifier(),
            authorization="Bearer authentic-token",
            declared_actor=None,
            required_scopes=("grc.policy.write",),
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "required scope" not in str(exc.detail)
    else:
        raise AssertionError("missing scope must be forbidden")


def test_keyverse_tenant_owned_policies_are_isolated_by_org_claim() -> None:
    """The same officer in another Keyverse org cannot read or revise tenant records."""
    private_key, jwk = _signing_material("key-1")
    client = _client(_verifier(jwk))
    acme_token = _token(private_key, org="tenant-acme", jti="token-acme-1")
    other_token = _token(private_key, org="tenant-other", jti="token-other-1")
    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {acme_token}",
            "X-Purpose": "policy_authoring",
        },
        json={
            "policy_title": "Acme Retention Policy",
            "policy_body": "Keep CSAP 10.2.1 grants for the declared tenant.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["policy_document_id"]

    other_list = client.get(
        "/policy-documents",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_list.status_code == 200
    assert other_list.json()["policies"] == []

    other_home = client.get("/", headers={"Authorization": f"Bearer {other_token}"})
    assert "Acme Retention Policy" not in other_home.text

    revised = client.post(
        f"/policy-documents/{policy_id}/versions",
        headers={
            "Authorization": f"Bearer {other_token}",
            "X-Purpose": "policy_authoring",
        },
        json={"policy_body": "Cross-tenant rewrite.", "control_refs": []},
    )
    assert revised.status_code == 404

    evidence = client.post(
        "/evidence-records",
        headers={
            "Authorization": f"Bearer {acme_token}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "evidence_title": "Acme CSAP 10.2.1 register",
            "payload_text": "Officer Park approved unique user IDs.",
        },
    )
    assert evidence.status_code == 201
    bound = client.post(
        "/control-evidence-bindings",
        headers={
            "Authorization": f"Bearer {other_token}",
            "X-Purpose": "evidence_binding",
        },
        json={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "10.2.1",
            "evidence_record_id": evidence.json()["evidence_record_id"],
        },
    )
    assert bound.status_code == 404


def test_officer_home_hides_other_officers_policy_title_under_keyverse() -> None:
    """officer-kim must not see officer-park's CSAP 10.2.1 policy title on GET /."""
    private_key, jwk = _signing_material("key-1")
    client = _client(_verifier(jwk))
    park_token = _token(private_key)
    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {park_token}",
            "X-Purpose": "policy_authoring",
        },
        json={
            "policy_title": "Park Logical Access Policy",
            "policy_body": "Least privilege for CSAP 10.2.1.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 201

    denied = client.get("/")
    assert denied.status_code == 401

    park_home = client.get("/", headers={"Authorization": f"Bearer {park_token}"})
    assert park_home.status_code == 200
    assert "Park Logical Access Policy" in park_home.text
    assert "10.2.1" in park_home.text

    kim_token = _token(private_key, sub="officer-kim", jti="token-kim-home")
    kim_home = client.get("/", headers={"Authorization": f"Bearer {kim_token}"})
    assert kim_home.status_code == 200
    assert "Park Logical Access Policy" not in kim_home.text

    kim_form = client.post(
        "/officer/policy",
        headers={"Authorization": f"Bearer {kim_token}"},
        data={
            "policy_title": "Kim Access Policy",
            "policy_body": "Kim authors a different policy.",
            "actor_identifier": "officer-kim",
            "control_refs": [f"{FrameworkCode.CSAP_2026.value}|10.2.1"],
        },
        follow_redirects=False,
    )
    assert kim_form.status_code == 303
    follow = client.get("/", headers={"Authorization": f"Bearer {kim_token}"})
    assert "Kim Access Policy" in follow.text
    assert "Park Logical Access Policy" not in follow.text

    evidence = client.post(
        "/officer/evidence",
        headers={"Authorization": f"Bearer {kim_token}"},
        data={
            "actor_identifier": "officer-kim",
            "evidence_title": "CSAP 10.2.1 access-grant register",
            "payload_text": "Kim recorded the quarterly access review.",
            "control_ref": f"{FrameworkCode.CSAP_2026.value}|10.2.1",
        },
        follow_redirects=False,
    )
    assert evidence.status_code == 303


def test_local_preview_still_accepts_declared_actor_without_keyverse() -> None:
    """The unauthenticated developer preview keeps the existing officer header contract."""
    client = _client()
    created = client.post(
        "/policy-documents",
        headers={"X-Actor-Id": "officer-preview", "X-Purpose": "policy_authoring"},
        json={
            "policy_title": "Local Preview Policy",
            "policy_body": "Local declarations are not authentication.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert created.status_code == 201
    listed = client.get("/policy-documents")
    assert listed.status_code == 200
    assert listed.json()["policies"][0]["policy_title"] == "Local Preview Policy"


def test_bearer_extraction_rejects_malformed_authorization_values() -> None:
    """Only a single compact Bearer token is accepted."""
    from fastapi import HTTPException

    from cwl_grc.keyverse_http import extract_bearer_token

    for value in (None, "Basic abc", "Bearer", "Bearer  token", "Bearer a b"):
        try:
            extract_bearer_token(value)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("malformed authorization must fail closed")
    assert extract_bearer_token("Bearer compact-token") == "compact-token"


def test_openapi_publishes_keyverse_bearer_on_officer_routes() -> None:
    """Officer policy and evidence operations declare Keyverse Bearer scopes."""
    client = _client()
    first = client.get("/openapi.json")
    second = client.get("/openapi.json")
    assert first.status_code == 200
    assert second.json() == first.json()
    spec = first.json()
    scheme = spec["components"]["securitySchemes"]["KeyverseBearer"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert scheme["bearerFormat"] == "at+jwt"
    assert "grc.policy.read" in scheme["description"]
    assert "grc.policy.write" in scheme["description"]
    assert "grc.evidence.write" in scheme["description"]
    assert spec["paths"]["/policy-documents"]["post"]["security"] == [
        {"KeyverseBearer": ["grc.policy.write"]}
    ]
    assert spec["paths"]["/policy-documents"]["get"]["security"] == [
        {"KeyverseBearer": ["grc.policy.read"]}
    ]
    assert spec["paths"]["/evidence-records"]["post"]["security"] == [
        {"KeyverseBearer": ["grc.evidence.write"]}
    ]
    assert spec["paths"]["/"]["get"]["security"] == [
        {"KeyverseBearer": ["grc.policy.read"]}
    ]
    assert "security" not in spec["paths"]["/healthz"]["get"]
    assert "security" not in spec["paths"]["/controls"]["get"]
