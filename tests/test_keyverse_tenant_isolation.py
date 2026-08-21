"""RED contracts for tenant-owned GRC records and protected tenant reads."""

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
from cwl_grc.models import (
    AuditEvent,
    ControlEvidenceBinding,
    EvidenceRecord,
    PolicyControlMapping,
    PolicyDocument,
    PolicyVersion,
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=timezone.utc)
ISSUER = "https://identity.example.test/realms/cwl"
AUDIENCE = "cwl-grc-api"
CLIENT_ID = "cwl-grc-web"
ROLE = "compliance_officer"
SOC2_FRAMEWORK = "soc2_tsc_2017"


def _material() -> tuple[Any, dict[str, Any]]:
    """Return one private RSA key and matching public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "tenant-key-1", "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _client(public_jwk: dict[str, Any]) -> TestClient:
    """Create one isolated Keyverse-enabled GRC application."""
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


def _token(private_key: Any, *, tenant_id: str, scope: str) -> str:
    """Sign one exact human access token for a tenant and scope set."""
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": f"officer-{tenant_id}",
            "aud": AUDIENCE,
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
            "nbf": int((NOW - timedelta(seconds=1)).timestamp()),
            "iat": int((NOW - timedelta(seconds=1)).timestamp()),
            "jti": f"token-{tenant_id}-{scope}",
            "client_id": CLIENT_ID,
            "scope": scope,
            "role": ROLE,
            "org": tenant_id,
            "workspace": f"workspace-{tenant_id}",
            "principal_kind": "human",
        },
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "tenant-key-1"},
    )


def _headers(private_key: Any, *, tenant_id: str, scope: str, purpose: str) -> dict[str, str]:
    """Return signed bearer and declared-purpose request headers."""
    return {
        "Authorization": f"Bearer {_token(private_key, tenant_id=tenant_id, scope=scope)}",
        "X-Purpose": purpose,
    }


def _policy_body() -> dict[str, Any]:
    """Return one realistic policy payload mapped to the official SOC 2 catalog."""
    return {
        "policy_title": "Quarterly access review",
        "policy_body": "Review privileged access every quarter and retain evidence.",
        "control_refs": [
            {
                "framework": SOC2_FRAMEWORK,
                "catalog_identifier": "CC1.1",
            }
        ],
    }


def _create_policy(client: TestClient, private_key: Any, tenant_id: str) -> str:
    """Create one policy as a verified tenant officer and return its identifier."""
    response = client.post(
        "/policy-documents",
        headers=_headers(
            private_key,
            tenant_id=tenant_id,
            scope="grc.policy.write",
            purpose="policy_authoring",
        ),
        json=_policy_body(),
    )
    assert response.status_code == 201
    return str(response.json()["policy_document_id"])


def _create_evidence(client: TestClient, private_key: Any, tenant_id: str) -> str:
    """Create one exact-value evidence record as a verified tenant officer."""
    response = client.post(
        "/evidence-records",
        headers=_headers(
            private_key,
            tenant_id=tenant_id,
            scope="grc.evidence.write",
            purpose="evidence_binding",
        ),
        json={
            "evidence_title": "Quarterly access review evidence",
            "payload_text": "Reviewed privileged access on 2026-08-19.",
        },
    )
    assert response.status_code == 201
    return str(response.json()["evidence_record_id"])


def test_tenant_owned_models_persist_exact_tenant_key() -> None:
    """Every tenant-owned record must carry the verified external tenant key."""
    for model in (
        PolicyDocument,
        PolicyVersion,
        PolicyControlMapping,
        EvidenceRecord,
        ControlEvidenceBinding,
        AuditEvent,
    ):
        assert "tenant_id" in model.__table__.columns
        assert model.__table__.columns["tenant_id"].nullable is False


def test_policy_list_requires_verified_read_scope() -> None:
    """Policy bodies are protected reads once Keyverse authentication is enabled."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    _create_policy(client, private_key, "tenant-a")

    missing = client.get("/policy-documents")
    wrong_scope = client.get(
        "/policy-documents",
        headers=_headers(
            private_key,
            tenant_id="tenant-a",
            scope="grc.evidence.write",
            purpose="coverage_review",
        ),
    )
    allowed = client.get(
        "/policy-documents",
        headers=_headers(
            private_key,
            tenant_id="tenant-a",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )

    assert missing.status_code == 401
    assert wrong_scope.status_code == 403
    assert allowed.status_code == 200
    assert len(allowed.json()["policies"]) == 1


def test_policy_list_never_crosses_verified_tenant_boundary() -> None:
    """A valid officer must not observe another tenant's policy existence or body."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    policy_document_id = _create_policy(client, private_key, "tenant-a")

    response = client.get(
        "/policy-documents",
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )

    assert response.status_code == 200
    assert response.json()["policies"] == []
    assert policy_document_id not in response.text


def test_policy_gap_read_is_authenticated_and_tenant_scoped() -> None:
    """Gap reads require policy-read scope and reveal only the verified tenant's gaps."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    policy_document_id = _create_policy(client, private_key, "tenant-a")

    missing = client.get("/policy-gaps")
    cross_tenant = client.get(
        "/policy-gaps",
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )
    own_tenant = client.get(
        "/policy-gaps",
        headers=_headers(
            private_key,
            tenant_id="tenant-a",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )

    assert missing.status_code == 401
    assert cross_tenant.status_code == 200
    assert cross_tenant.json()["gaps"] == []
    assert policy_document_id not in cross_tenant.text
    assert own_tenant.status_code == 200
    assert len(own_tenant.json()["gaps"]) == 1


def test_coverage_and_officer_console_reads_use_verified_tenant() -> None:
    """Coverage bindings and the officer console never cross tenant boundaries."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    evidence_record_id = _create_evidence(client, private_key, "tenant-a")
    bound = client.post(
        "/control-evidence-bindings",
        headers=_headers(
            private_key,
            tenant_id="tenant-a",
            scope="grc.evidence.write",
            purpose="evidence_binding",
        ),
        json={
            "framework": SOC2_FRAMEWORK,
            "catalog_identifier": "CC1.1",
            "evidence_record_id": evidence_record_id,
        },
    )
    assert bound.status_code == 201

    missing_coverage_auth = client.get(
        "/controls/uncovered",
        params={"framework": SOC2_FRAMEWORK},
    )
    tenant_a_coverage = client.get(
        "/controls/uncovered",
        params={"framework": SOC2_FRAMEWORK},
        headers=_headers(
            private_key,
            tenant_id="tenant-a",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )
    tenant_b_coverage = client.get(
        "/controls/uncovered",
        params={"framework": SOC2_FRAMEWORK},
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )
    missing_home_auth = client.get("/")
    tenant_b_home = client.get(
        "/",
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.policy.read",
            purpose="coverage_review",
        ),
    )

    tenant_a_ids = {item["catalog_identifier"] for item in tenant_a_coverage.json()["controls"]}
    tenant_b_ids = {item["catalog_identifier"] for item in tenant_b_coverage.json()["controls"]}
    assert missing_coverage_auth.status_code == 401
    assert tenant_a_coverage.status_code == 200
    assert tenant_b_coverage.status_code == 200
    assert "CC1.1" not in tenant_a_ids
    assert "CC1.1" in tenant_b_ids
    assert missing_home_auth.status_code == 401
    assert tenant_b_home.status_code == 200


def test_policy_revision_hides_cross_tenant_object_reference() -> None:
    """A tenant B writer cannot revise a tenant A policy by guessing its identifier."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    policy_document_id = _create_policy(client, private_key, "tenant-a")

    response = client.post(
        f"/policy-documents/{policy_document_id}/versions",
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.policy.write",
            purpose="policy_authoring",
        ),
        json={
            "policy_body": "Attacker-controlled cross-tenant replacement.",
            "control_refs": [],
        },
    )

    assert response.status_code == 404


def test_evidence_binding_hides_cross_tenant_object_reference() -> None:
    """A tenant B writer cannot bind tenant A evidence to any control."""
    private_key, public_jwk = _material()
    client = _client(public_jwk)
    evidence_record_id = _create_evidence(client, private_key, "tenant-a")

    response = client.post(
        "/control-evidence-bindings",
        headers=_headers(
            private_key,
            tenant_id="tenant-b",
            scope="grc.evidence.write",
            purpose="evidence_binding",
        ),
        json={
            "framework": SOC2_FRAMEWORK,
            "catalog_identifier": "CC1.1",
            "evidence_record_id": evidence_record_id,
        },
    )

    assert response.status_code == 404
