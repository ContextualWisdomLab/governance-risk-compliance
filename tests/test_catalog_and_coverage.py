"""Failing buyer tests for catalog listing, evidence binding, and coverage gaps."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.catalog import FrameworkCode


def _client() -> TestClient:
    """Return a TestClient against an isolated in-memory product."""
    return TestClient(create_app(database_url="sqlite://", evidence_key=None))


def test_healthz_reports_ok() -> None:
    response = _client().get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "cwl-grc"


def test_lists_real_soc2_isms_p_and_csap_identifiers() -> None:
    client = _client()
    soc2 = client.get("/controls", params={"framework": FrameworkCode.SOC2_TSC_2017.value})
    isms = client.get("/controls", params={"framework": FrameworkCode.ISMS_P_2023.value})
    csap = client.get("/controls", params={"framework": FrameworkCode.CSAP_2026.value})
    assert soc2.status_code == 200
    identifiers = {item["catalog_identifier"] for item in soc2.json()["controls"]}
    assert {"CC1.1", "CC5.3", "CC6.1", "CC6.2", "CC6.3", "P3.1"} <= identifiers
    isms_ids = {item["catalog_identifier"] for item in isms.json()["controls"]}
    assert {"1.1.1", "2.5.1", "3.1.1", "3.1.2"} <= isms_ids
    assert next(item["control_title"] for item in isms.json()["controls"] if item["catalog_identifier"] == "3.1.1") == (
        "개인정보 수집∙이용"
    )
    csap_ids = {item["catalog_identifier"] for item in csap.json()["controls"]}
    assert {"1.1.1", "10.2.1", "10.3.1", "12.3.1"} <= csap_ids


def test_lists_iso_nist_and_coso_identifiers() -> None:
    client = _client()
    iso = client.get("/controls", params={"framework": FrameworkCode.ISO27001_2022.value}).json()
    nist = client.get("/controls", params={"framework": FrameworkCode.NIST_SP_800_53_R5.value}).json()
    ic = client.get("/controls", params={"framework": FrameworkCode.COSO_IC_2013.value}).json()
    erm = client.get("/controls", params={"framework": FrameworkCode.COSO_ERM_2017.value}).json()
    assert {"A.5.1", "A.8.2", "A.8.15"} <= {item["catalog_identifier"] for item in iso["controls"]}
    assert {"AC-2", "AU-2", "IA-2"} <= {item["catalog_identifier"] for item in nist["controls"]}
    assert {"Principle 1", "Principle 10", "Principle 12"} <= {
        item["catalog_identifier"] for item in ic["controls"]
    }
    assert {"Principle 13", "Principle 20"} <= {item["catalog_identifier"] for item in erm["controls"]}


def test_unknown_framework_is_rejected() -> None:
    response = _client().get("/controls", params={"framework": "toy-catalog"})
    assert response.status_code == 400


def test_uncovered_csap_control_until_officer_binds_evidence() -> None:
    client = _client()
    headers = {
        "X-Actor-Id": "officer-ahn",
        "X-Purpose": "evidence_binding",
    }
    gaps = client.get("/controls/uncovered", params={"framework": FrameworkCode.CSAP_2026.value})
    assert gaps.status_code == 200
    uncovered = {item["catalog_identifier"] for item in gaps.json()["controls"]}
    assert "10.2.1" in uncovered
    created = client.post(
        "/evidence-records",
        headers=headers,
        json={
            "evidence_title": "CSAP 10.2.1 access-grant register",
            "payload_text": "Officer Ahn (ahn@example.go.kr) approved unique user IDs on 2026-08-01.",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert "ahn@example.go.kr" in body["payload_text"]
    bind = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "10.2.1",
            "evidence_record_id": body["evidence_record_id"],
        },
    )
    assert bind.status_code == 201
    after = client.get("/controls/uncovered", params={"framework": FrameworkCode.CSAP_2026.value})
    assert "10.2.1" not in {item["catalog_identifier"] for item in after.json()["controls"]}
    assert "10.3.1" in {item["catalog_identifier"] for item in after.json()["controls"]}


def test_soc2_cc6_1_and_isms_p_2_5_1_bind_independently() -> None:
    client = _client()
    headers = {"X-Actor-Id": "officer-park", "X-Purpose": "evidence_binding"}
    evidence = client.post(
        "/evidence-records",
        headers=headers,
        json={
            "evidence_title": "Logical access architecture review",
            "payload_text": "Contact: park@example.co.kr",
        },
    ).json()
    soc2 = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.SOC2_TSC_2017.value,
            "catalog_identifier": "CC6.1",
            "evidence_record_id": evidence["evidence_record_id"],
        },
    )
    isms = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.ISMS_P_2023.value,
            "catalog_identifier": "2.5.1",
            "evidence_record_id": evidence["evidence_record_id"],
        },
    )
    assert soc2.status_code == 201
    assert isms.status_code == 201
    soc2_gaps = {
        item["catalog_identifier"]
        for item in client.get(
            "/controls/uncovered",
            params={"framework": FrameworkCode.SOC2_TSC_2017.value},
        ).json()["controls"]
    }
    isms_gaps = {
        item["catalog_identifier"]
        for item in client.get(
            "/controls/uncovered",
            params={"framework": FrameworkCode.ISMS_P_2023.value},
        ).json()["controls"]
    }
    assert "CC6.1" not in soc2_gaps
    assert "CC6.2" in soc2_gaps
    assert "2.5.1" not in isms_gaps
    assert "2.5.3" in isms_gaps


def test_duplicate_binding_is_conflict() -> None:
    client = _client()
    headers = {"X-Actor-Id": "officer-choi", "X-Purpose": "evidence_binding"}
    evidence = client.post(
        "/evidence-records",
        headers=headers,
        json={"evidence_title": "ISMS-P 3.1.2 minimum collection", "payload_text": "choi@example.go.kr"},
    ).json()
    payload = {
        "framework": FrameworkCode.ISMS_P_2023.value,
        "catalog_identifier": "3.1.2",
        "evidence_record_id": evidence["evidence_record_id"],
    }
    assert client.post("/control-evidence-bindings", headers=headers, json=payload).status_code == 201
    assert client.post("/control-evidence-bindings", headers=headers, json=payload).status_code == 409


def test_unknown_control_or_evidence_is_not_found() -> None:
    client = _client()
    headers = {"X-Actor-Id": "officer-lee", "X-Purpose": "evidence_binding"}
    missing_control = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.SOC2_TSC_2017.value,
            "catalog_identifier": "CC99.9",
            "evidence_record_id": "missing-evidence",
        },
    )
    assert missing_control.status_code == 404
    created = client.post(
        "/evidence-records",
        headers=headers,
        json={"evidence_title": "Orphan artifact", "payload_text": "lee@example.go.kr"},
    ).json()
    missing_id = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={
            "framework": FrameworkCode.SOC2_TSC_2017.value,
            "catalog_identifier": "CC6.1",
            "evidence_record_id": "does-not-exist",
        },
    )
    assert missing_id.status_code == 404
    assert created["evidence_record_id"]


def test_evidence_requires_purpose_limited_actor() -> None:
    client = _client()
    denied = client.post(
        "/evidence-records",
        json={"evidence_title": "Denied", "payload_text": "secret"},
    )
    assert denied.status_code == 401
    wrong = client.post(
        "/evidence-records",
        headers={"X-Actor-Id": "officer-kim", "X-Purpose": "coverage_review"},
        json={"evidence_title": "Wrong purpose", "payload_text": "secret"},
    )
    assert wrong.status_code == 403
    unknown = client.post(
        "/evidence-records",
        headers={"X-Actor-Id": "officer-kim", "X-Purpose": "exfiltrate"},
        json={"evidence_title": "Unknown purpose", "payload_text": "secret"},
    )
    assert unknown.status_code == 403


def test_officer_home_states_next_action_for_uncovered_control() -> None:
    page = _client().get("/")
    assert page.status_code == 200
    text = page.text
    assert "10.2.1" in text
    assert "CC6.1" in text
    assert "2.5.1" in text
    assert "Attach the next evidence" in text


def test_lists_every_seeded_framework_when_unfiltered() -> None:
    response = _client().get("/controls")
    frameworks = {item["framework"] for item in response.json()["controls"]}
    assert FrameworkCode.NIST_SP_800_53_R5.value in frameworks
    assert FrameworkCode.ISO27001_2022.value in frameworks


def test_empty_evidence_is_rejected() -> None:
    response = _client().post(
        "/evidence-records",
        headers={"X-Actor-Id": "officer-oh", "X-Purpose": "evidence_binding"},
        json={"evidence_title": " ", "payload_text": ""},
    )
    assert response.status_code == 400


def test_binding_requires_framework() -> None:
    client = _client()
    headers = {"X-Actor-Id": "officer-oh", "X-Purpose": "evidence_binding"}
    evidence = client.post(
        "/evidence-records",
        headers=headers,
        json={"evidence_title": "NIST AC-2 roster", "payload_text": "oh@example.go.kr"},
    ).json()
    response = client.post(
        "/control-evidence-bindings",
        headers=headers,
        json={"catalog_identifier": "AC-2", "evidence_record_id": evidence["evidence_record_id"]},
    )
    assert response.status_code == 400


def test_officer_form_accepts_control_ref() -> None:
    client = _client()
    posted = client.post(
        "/officer/evidence",
        data={
            "control_ref": f"{FrameworkCode.SOC2_TSC_2017.value}|CC7.2",
            "actor_identifier": "officer-han",
            "evidence_title": "SOC 2 CC7.2 monitoring extract",
            "payload_text": "han@example.co.kr",
        },
        follow_redirects=False,
    )
    assert posted.status_code == 303
    invalid = client.post(
        "/officer/evidence",
        data={
            "control_ref": "not-a-ref",
            "actor_identifier": "officer-han",
            "evidence_title": "Broken ref",
            "payload_text": "han@example.co.kr",
        },
    )
    assert invalid.status_code == 400
    missing = client.post(
        "/officer/evidence",
        data={
            "actor_identifier": "officer-han",
            "evidence_title": "No control",
            "payload_text": "han@example.co.kr",
        },
    )
    assert missing.status_code == 400


def test_officer_can_bind_evidence_from_home_form() -> None:
    client = _client()
    posted = client.post(
        "/officer/evidence",
        data={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "12.3.1",
            "actor_identifier": "officer-jung",
            "evidence_title": "CSAP 12.3.1 cipher policy",
            "payload_text": "jung@example.go.kr approved TLS 1.3.",
        },
        follow_redirects=False,
    )
    assert posted.status_code in {201, 303}
    gaps = client.get("/controls/uncovered", params={"framework": FrameworkCode.CSAP_2026.value})
    assert "12.3.1" not in {item["catalog_identifier"] for item in gaps.json()["controls"]}
