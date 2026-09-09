"""Verify the real GRC routes cannot mutate from an untrusted browser context."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cwl_grc import create_app


def test_cross_origin_form_does_not_create_policy() -> None:
    """Inspect persisted policy results, not only the boundary's response code."""
    with TestClient(create_app(database_url="sqlite://", evidence_key=None)) as client:
        policy_form = {
            "policy_title": "Unit-test access policy",
            "policy_body": "Synthetic unit-test policy body.",
            "actor_identifier": "unit_test_officer",
            "control_refs": "csap_2026|10.2.1",
        }
        assert client.get("/policy-documents").json()["policies"] == []
        for origin_value in ("https://untrusted.example", "null", "http://testserver:8080"):
            response = client.post(
                "/officer/policy", headers={"Origin": origin_value},
                data=policy_form, follow_redirects=False,
            )
            assert response.status_code == 403
        assert client.get("/policy-documents").json()["policies"] == []
        accepted = client.post(
            "/officer/policy", headers={"Origin": "http://testserver"},
            data=policy_form, follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert len(client.get("/policy-documents").json()["policies"]) == 1
        assert accepted.headers["cache-control"] == "no-store"


def test_originless_form_and_forwarded_request_are_not_intent() -> None:
    """An unverified form or empty proxy header cannot reach the domain handlers."""
    with TestClient(create_app(database_url="sqlite://", evidence_key=None)) as client:
        assert client.post("/officer/evidence", data={"actor_identifier": "unit_test_officer"}).status_code == 403
        assert client.get("/healthz", headers={"Forwarded": ""}).status_code == 503
        assert client.get("/healthz", headers={"Host": "untrusted.example"}).status_code == 403


def test_local_json_evidence_remains_exact_and_non_cacheable() -> None:
    """Keep explicit-purpose preview use without adding implicit identity claims."""
    with TestClient(create_app(database_url="sqlite://", evidence_key=None)) as client:
        response = client.post(
            "/evidence-records",
            headers={"X-Actor-Id": "unit_test_officer", "X-Purpose": "evidence_binding"},
            json={"evidence_title": "Unit-test record", "payload_text": "Synthetic unit-test value."},
        )
        assert response.status_code == 201
        assert response.json()["payload_text"] == "Synthetic unit-test value."
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_handled_errors_and_reads_have_privacy_headers() -> None:
    """Exercise application validation and read responses, not outer server crashes."""
    with TestClient(create_app(database_url="sqlite://", evidence_key=None)) as client:
        for response in (
            client.get("/"), client.get("/healthz"), client.get("/policy-documents"),
            client.get("/controls", params={"framework": "unit_test_unknown"}),
            client.post("/evidence-records", json={}), client.get("/unit_test_missing"),
        ):
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["pragma"] == "no-cache"
