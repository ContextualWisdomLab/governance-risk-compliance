"""Contract tests for the truthful workspace-posture preview."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cwl_grc.app import create_app
from cwl_grc.catalog import FrameworkCode


def _client() -> TestClient:
    """Return an isolated local-preview client."""
    return TestClient(create_app(database_url="sqlite://", evidence_key=None))


def _legacy_binding(client: TestClient) -> None:
    """Create one realistic legacy evidence binding for the projection test."""
    headers = {"X-Actor-Id": "officer-preview", "X-Purpose": "evidence_binding"}
    evidence = client.post(
        "/evidence-records",
        headers=headers,
        json={
            "evidence_title": "CSAP access review register",
            "payload_text": "Authorized local preview evidence.",
        },
    )
    assert evidence.status_code == 201
    binding = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "10.2.1",
            "evidence_record_id": evidence.json()["evidence_record_id"],
        },
    )
    assert binding.status_code == 201


def test_posture_preview_exposes_truthful_not_assessed_boundary() -> None:
    """The empty local store must not be presented as effective compliance."""
    response = _client().get("/workspace/posture")

    assert response.status_code == 200
    body = response.json()
    assert body["projection"] == "workspace_posture"
    assert body["availability"] == "local_developer_preview"
    assert body["posture_status"] == "not_assessed"
    assert body["authorization"]["status"] == "not_configured"
    assert body["metrics"]["official_control_count"] > 0
    assert body["metrics"]["legacy_evidence_only_count"] == 0
    assert body["metrics"]["effective_control_count"] == 0
    assert (
        body["metrics"]["not_assessed_control_count"]
        == body["metrics"]["official_control_count"]
    )
    assert {row["status"] for row in body["exact_value_rows"]} == {"not_assessed"}
    assert all(row["catalog_edition"] for row in body["exact_value_rows"])
    assert all(
        row["catalog_source_url"].startswith("https://")
        for row in body["exact_value_rows"]
    )
    assert body["policy_gap_rows"] == []
    assert all("payload_text" not in row for row in body["exact_value_rows"])


def test_legacy_evidence_remains_unknown_until_effectiveness_exists() -> None:
    """A legacy binding changes evidence state but never creates effectiveness."""
    client = _client()
    _legacy_binding(client)

    body = client.get("/workspace/posture").json()
    row = next(item for item in body["exact_value_rows"] if item["catalog_identifier"] == "10.2.1")

    assert row["status"] == "unknown"
    assert "effectiveness" in row["reason"]
    assert row["catalog_edition"] == "2026.07"
    assert body["metrics"]["legacy_evidence_only_count"] == 1
    assert body["metrics"]["effective_control_count"] == 0


def test_posture_reports_policy_gap_count_without_claiming_certification() -> None:
    """A mapped policy gap is counted while the preview remains explicitly incomplete."""
    client = _client()
    authored = client.post(
        "/policy-documents",
        headers={"X-Actor-Id": "officer-preview", "X-Purpose": "policy_authoring"},
        json={
            "policy_title": "Logical Access Policy",
            "policy_body": "Review access grants quarterly.",
            "control_refs": [
                {
                    "framework": FrameworkCode.CSAP_2026.value,
                    "catalog_identifier": "10.2.1",
                }
            ],
        },
    )
    assert authored.status_code == 201

    body = client.get("/workspace/posture").json()

    assert body["metrics"]["policy_gap_count"] == 1
    assert body["policy_gap_rows"][0]["catalog_identifier"] == "10.2.1"
    assert body["posture_status"] == "not_assessed"
    assert any("internal controls" in action for action in body["next_actions"])
