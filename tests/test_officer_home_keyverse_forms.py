"""Officer home forms send Keyverse Bearer tokens and purpose headers."""

from __future__ import annotations

from cwl_grc.catalog import FrameworkCode
from test_keyverse_http_route_enforcement import (
    _client,
    _signing_material,
    _token,
    _verifier,
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
    assert "X-Actor-Id" not in home.text.split("<script>")[1]
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
