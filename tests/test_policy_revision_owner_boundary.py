"""Policy revision authority follows hardened officer-and-tenant ownership."""

from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from cwl_grc.app import create_app
from cwl_grc.database import create_session_factory
from cwl_grc.models import AuditEvent, PolicyVersion
from test_keyverse_http_route_enforcement import _signing_material, _token, _verifier


def test_same_tenant_colleague_cannot_revise_hidden_policy(tmp_path: Path) -> None:
    """A policy hidden from another officer cannot be revised by that officer."""
    private_key, jwk = _signing_material("key-1")
    database = tmp_path / "revision-owner.sqlite"
    database_url = f"sqlite:///{database}"
    client = TestClient(
        create_app(
            database_url=database_url,
            evidence_key=Fernet.generate_key().decode(),
            access_token_verifier=_verifier(jwk),
        )
    )
    park_token = _token(private_key, sub="officer-park", jti="token-park-owner")
    lee_token = _token(private_key, sub="officer-lee", jti="token-lee-owner")

    created = client.post(
        "/policy-documents",
        headers={
            "Authorization": f"Bearer {park_token}",
            "X-Purpose": "policy_authoring",
        },
        json={
            "policy_title": "Officer-owned access policy",
            "policy_body": "Initial approved edition.",
            "control_refs": [],
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["policy_document_id"]

    colleague_list = client.get(
        "/policy-documents",
        headers={"Authorization": f"Bearer {lee_token}"},
    )
    assert colleague_list.status_code == 200
    assert colleague_list.json()["policies"] == []
    colleague_gaps = client.get(
        "/policy-gaps",
        headers={"Authorization": f"Bearer {lee_token}"},
    )
    assert colleague_gaps.status_code == 200
    assert colleague_gaps.json()["gaps"] == []

    denied = client.post(
        f"/policy-documents/{policy_id}/versions",
        headers={
            "Authorization": f"Bearer {lee_token}",
            "X-Purpose": "policy_authoring",
        },
        json={"policy_body": "Unauthorized colleague edition.", "control_refs": []},
    )
    assert denied.status_code == 404
    assert denied.json()["detail"] == "That policy document is not on file."

    factory = create_session_factory(database_url)
    with factory() as session:
        assert session.query(PolicyVersion).filter_by(policy_document_id=policy_id).count() == 1
        assert session.query(AuditEvent).filter_by(action_name="revise_policy").count() == 0

    revised = client.post(
        f"/policy-documents/{policy_id}/versions",
        headers={
            "Authorization": f"Bearer {park_token}",
            "X-Purpose": "policy_authoring",
        },
        json={"policy_body": "Authorized second edition.", "control_refs": []},
    )
    assert revised.status_code == 201
    assert revised.json()["current_version"]["version_number"] == 2

    with factory() as session:
        assert session.query(PolicyVersion).filter_by(policy_document_id=policy_id).count() == 2
        assert session.query(AuditEvent).filter_by(action_name="revise_policy").count() == 1
