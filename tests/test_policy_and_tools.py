"""Failing tests for versioned policies, policy gaps, and the operator CLI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.catalog import FrameworkCode
from cwl_grc.cli import main as cli_main


def _client() -> TestClient:
    """Return a TestClient against an isolated in-memory product."""
    return TestClient(create_app(database_url="sqlite://", evidence_key=None))


def _author_headers() -> dict[str, str]:
    """Return purpose-limited headers for policy authoring."""
    return {"X-Actor-Id": "officer-ahn", "X-Purpose": "policy_authoring"}


def _bind_headers() -> dict[str, str]:
    """Return purpose-limited headers for evidence binding."""
    return {"X-Actor-Id": "officer-ahn", "X-Purpose": "evidence_binding"}


def test_officer_authors_policy_mapped_to_official_controls() -> None:
    client = _client()
    created = client.post(
        "/policy-documents",
        headers=_author_headers(),
        json={
            "policy_title": "Logical Access Policy",
            "policy_body": "Unique accounts, least privilege, and formal grant/revoke for cloud access.",
            "control_refs": [
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "10.2.1"},
                {"framework": FrameworkCode.SOC2_TSC_2017.value, "catalog_identifier": "CC6.1"},
                {"framework": FrameworkCode.ISMS_P_2023.value, "catalog_identifier": "2.5.1"},
                {"framework": FrameworkCode.ISO27001_2022.value, "catalog_identifier": "A.5.15"},
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["policy_title"] == "Logical Access Policy"
    assert body["current_version"]["version_number"] == 1
    mapped = {
        (item["framework"], item["catalog_identifier"])
        for item in body["current_version"]["mapped_controls"]
    }
    assert (
        FrameworkCode.CSAP_2026.value,
        "10.2.1",
    ) in mapped
    assert (FrameworkCode.SOC2_TSC_2017.value, "CC6.1") in mapped
    listed = client.get("/policy-documents")
    assert listed.status_code == 200
    assert any(item["policy_document_id"] == body["policy_document_id"] for item in listed.json()["policies"])


def test_policy_cannot_map_an_invented_control() -> None:
    response = _client().post(
        "/policy-documents",
        headers=_author_headers(),
        json={
            "policy_title": "Toy Policy",
            "policy_body": "Do not invent a second catalog.",
            "control_refs": [{"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "99.9.9"}],
        },
    )
    assert response.status_code == 404


def test_policy_version_replaces_mappings_on_the_new_edition() -> None:
    client = _client()
    created = client.post(
        "/policy-documents",
        headers=_author_headers(),
        json={
            "policy_title": "Cryptography Policy",
            "policy_body": "v1 maps CSAP cipher policy and ISO cryptography.",
            "control_refs": [
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "12.3.1"},
                {"framework": FrameworkCode.ISO27001_2022.value, "catalog_identifier": "A.8.24"},
            ],
        },
    ).json()
    revised = client.post(
        f"/policy-documents/{created['policy_document_id']}/versions",
        headers=_author_headers(),
        json={
            "policy_body": "v2 keeps CSAP 12.3.1 and adds ISMS-P 2.7.1.",
            "control_refs": [
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "12.3.1"},
                {"framework": FrameworkCode.ISMS_P_2023.value, "catalog_identifier": "2.7.1"},
            ],
        },
    )
    assert revised.status_code == 201
    version = revised.json()["current_version"]
    assert version["version_number"] == 2
    mapped = {item["catalog_identifier"] for item in version["mapped_controls"]}
    assert mapped == {"12.3.1", "2.7.1"}


def test_policy_gaps_use_the_same_control_evidence_bindings() -> None:
    client = _client()
    created = client.post(
        "/policy-documents",
        headers=_author_headers(),
        json={
            "policy_title": "Access Grant Policy",
            "policy_body": "Map CSAP 10.2.1 and SOC 2 CC6.2.",
            "control_refs": [
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "10.2.1"},
                {"framework": FrameworkCode.SOC2_TSC_2017.value, "catalog_identifier": "CC6.2"},
            ],
        },
    ).json()
    gaps = client.get("/policy-gaps", params={"policy_document_id": created["policy_document_id"]})
    assert gaps.status_code == 200
    assert gaps.json()["next_action"] == "Attach the next evidence on an uncovered policy control."
    uncovered = {item["catalog_identifier"] for item in gaps.json()["gaps"]}
    assert uncovered == {"10.2.1", "CC6.2"}
    evidence = client.post(
        "/evidence-records",
        headers=_bind_headers(),
        json={
            "evidence_title": "CSAP 10.2.1 grant register",
            "payload_text": "Officer Ahn (ahn@example.go.kr) approved unique user IDs.",
        },
    ).json()
    bind = client.post(
        "/control-evidence-bindings",
        headers=_bind_headers(),
        json={
            "framework": FrameworkCode.CSAP_2026.value,
            "catalog_identifier": "10.2.1",
            "evidence_record_id": evidence["evidence_record_id"],
        },
    )
    assert bind.status_code == 201
    after = client.get("/policy-gaps", params={"policy_document_id": created["policy_document_id"]})
    remaining = {item["catalog_identifier"] for item in after.json()["gaps"]}
    assert remaining == {"CC6.2"}


def test_policy_authoring_requires_purpose() -> None:
    denied = _client().post(
        "/policy-documents",
        json={"policy_title": "Denied", "policy_body": "No", "control_refs": []},
    )
    assert denied.status_code == 401
    wrong = _client().post(
        "/policy-documents",
        headers=_bind_headers(),
        json={"policy_title": "Wrong purpose", "policy_body": "No", "control_refs": []},
    )
    assert wrong.status_code == 403


def test_officer_home_lets_buyer_write_policy_and_see_policy_gaps() -> None:
    client = _client()
    home = client.get("/")
    assert "Author the next policy" in home.text
    posted = client.post(
        "/officer/policy",
        data={
            "policy_title": "Account Management Policy",
            "policy_body": "Register and revoke unique accounts.",
            "actor_identifier": "officer-jung",
            "control_refs": [
                f"{FrameworkCode.CSAP_2026.value}|10.2.1",
                f"{FrameworkCode.ISMS_P_2023.value}|2.5.1",
            ],
        },
        follow_redirects=True,
    )
    assert posted.status_code == 200
    assert "Account Management Policy" in posted.text
    assert "10.2.1" in posted.text
    assert "Attach the next evidence" in posted.text


def test_cli_authors_policy_lists_gaps_and_binds_evidence(tmp_path: Path, capsys) -> None:
    database = tmp_path / "grc_product.sqlite"
    env = {
        "CWL_GRC_DATABASE_URL": f"sqlite:///{database}",
        "CWL_GRC_EVIDENCE_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    }
    import os

    os.environ.update(env)
    try:
        assert (
            cli_main(
                [
                    "policy",
                    "author",
                    "--title",
                    "Logical Access Policy",
                    "--body",
                    "Least privilege for CSAP and SOC 2 access.",
                    "--map",
                    f"{FrameworkCode.CSAP_2026.value}:10.2.1",
                    "--map",
                    f"{FrameworkCode.SOC2_TSC_2017.value}:CC6.1",
                    "--actor",
                    "officer-park",
                ]
            )
            == 0
        )
        authored = json.loads(capsys.readouterr().out)
        assert authored["next_action"] == "Review policy gaps and attach the next evidence."
        assert cli_main(["gaps", "--policy-id", authored["policy_document_id"]]) == 0
        gaps = json.loads(capsys.readouterr().out)
        assert {item["catalog_identifier"] for item in gaps["gaps"]} == {"10.2.1", "CC6.1"}
        assert gaps["next_action"] == "Attach the next evidence on an uncovered policy control."
        assert (
            cli_main(
                [
                    "bind",
                    "--framework",
                    FrameworkCode.CSAP_2026.value,
                    "--identifier",
                    "10.2.1",
                    "--title",
                    "CSAP 10.2.1 register",
                    "--payload",
                    "park@example.co.kr approved the grant register.",
                    "--actor",
                    "officer-park",
                ]
            )
            == 0
        )
        bound = json.loads(capsys.readouterr().out)
        assert "ahn@example.go.kr" not in bound.get("payload_text", bound.get("next_action", ""))
        assert "park@example.co.kr" in json.dumps(bound)
        assert cli_main(["gaps", "--policy-id", authored["policy_document_id"]]) == 0
        remaining = json.loads(capsys.readouterr().out)
        assert {item["catalog_identifier"] for item in remaining["gaps"]} == {"CC6.1"}
        assert cli_main(["policy", "list"]) == 0
        listed = json.loads(capsys.readouterr().out)
        assert listed["policies"][0]["policy_title"] == "Logical Access Policy"
        assert (
            cli_main(
                [
                    "policy",
                    "revise",
                    "--policy-id",
                    authored["policy_document_id"],
                    "--body",
                    "v2 maps CSAP 12.3.1 cipher policy.",
                    "--map",
                    f"{FrameworkCode.CSAP_2026.value}:12.3.1",
                    "--actor",
                    "officer-park",
                ]
            )
            == 0
        )
        revised = json.loads(capsys.readouterr().out)
        assert revised["current_version"]["version_number"] == 2
        assert cli_main(["gaps"]) == 0
        unfiltered = json.loads(capsys.readouterr().out)
        assert {item["catalog_identifier"] for item in unfiltered["gaps"]} == {"12.3.1"}
    finally:
        os.environ.pop("CWL_GRC_DATABASE_URL", None)
        os.environ.pop("CWL_GRC_EVIDENCE_KEY", None)


def test_policy_validation_and_gap_lookup_errors() -> None:
    client = _client()
    headers = _author_headers()
    empty = client.post(
        "/policy-documents",
        headers=headers,
        json={"policy_title": " ", "policy_body": "", "control_refs": []},
    )
    assert empty.status_code == 400
    omitted_refs = client.post(
        "/policy-documents",
        headers=headers,
        json={"policy_title": "No mapped controls yet", "policy_body": "Author first, map on the next edition."},
    )
    assert omitted_refs.status_code == 201
    assert omitted_refs.json()["current_version"]["mapped_controls"] == []
    not_a_list = client.post(
        "/policy-documents",
        headers=headers,
        json={"policy_title": "Bad refs", "policy_body": "Body", "control_refs": "CC6.1"},
    )
    assert not_a_list.status_code == 400
    not_a_dict = client.post(
        "/policy-documents",
        headers=headers,
        json={"policy_title": "Bad ref item", "policy_body": "Body", "control_refs": ["CC6.1"]},
    )
    assert not_a_dict.status_code == 400
    unknown_framework = client.post(
        "/policy-documents",
        headers=headers,
        json={
            "policy_title": "Unknown framework",
            "policy_body": "Body",
            "control_refs": [{"framework": "toy-catalog", "catalog_identifier": "10.2.1"}],
        },
    )
    assert unknown_framework.status_code == 400
    missing_id = client.post(
        "/policy-documents",
        headers=headers,
        json={
            "policy_title": "Missing identifier",
            "policy_body": "Body",
            "control_refs": [{"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": " "}],
        },
    )
    assert missing_id.status_code == 400
    created = client.post(
        "/policy-documents",
        headers=headers,
        json={
            "policy_title": "Duplicate map Policy",
            "policy_body": "Same official control twice is one mapping.",
            "control_refs": [
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "10.2.1"},
                {"framework": FrameworkCode.CSAP_2026.value, "catalog_identifier": "10.2.1"},
            ],
        },
    )
    assert created.status_code == 201
    assert len(created.json()["current_version"]["mapped_controls"]) == 1
    missing_policy = client.post(
        "/policy-documents/missing/versions",
        headers=headers,
        json={"policy_body": "No", "control_refs": []},
    )
    assert missing_policy.status_code == 404
    blank_revision = client.post(
        f"/policy-documents/{created.json()['policy_document_id']}/versions",
        headers=headers,
        json={"policy_body": "  ", "control_refs": []},
    )
    assert blank_revision.status_code == 400
    assert client.get("/policy-gaps", params={"policy_document_id": "missing"}).status_code == 404
    unfiltered = client.get("/policy-gaps")
    assert unfiltered.status_code == 200
    assert "10.2.1" in {item["catalog_identifier"] for item in unfiltered.json()["gaps"]}


def test_officer_policy_form_rejects_invalid_control_refs() -> None:
    client = _client()
    invalid = client.post(
        "/officer/policy",
        data={
            "policy_title": "Broken",
            "policy_body": "No",
            "actor_identifier": "officer-jung",
            "control_refs": "not-a-ref",
        },
    )
    assert invalid.status_code == 400
    unknown = client.post(
        "/officer/policy",
        data={
            "policy_title": "Broken framework",
            "policy_body": "No",
            "actor_identifier": "officer-jung",
            "control_refs": "toy-catalog|10.2.1",
        },
    )
    assert unknown.status_code == 400


def test_cli_serve_and_error_paths(tmp_path: Path, capsys, monkeypatch) -> None:
    import os
    from argparse import Namespace

    from cwl_grc.cli import _dispatch, _policy_command, main as cli_entry

    captured: dict[str, object] = {}

    def fake_run(app, host, port):  # noqa: ANN001
        captured["host"] = host
        captured["port"] = port
        captured["title"] = app.title

    monkeypatch.setattr("cwl_grc.cli.uvicorn.run", fake_run)
    assert cli_main(["serve"]) == 0
    assert captured == {"host": "0.0.0.0", "port": 8080, "title": "CWL GRC"}
    monkeypatch.setenv("PORT", "9098")
    assert cli_main([]) == 0
    assert captured["port"] == 9098
    monkeypatch.setattr("sys.argv", ["cwl-grc"])
    assert cli_entry() == 0
    assert cli_main(["policy"]) == 2
    database = tmp_path / "grc_errors.sqlite"
    monkeypatch.setenv("CWL_GRC_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("CWL_GRC_EVIDENCE_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Toy",
                "--body",
                "Invented",
                "--map",
                f"{FrameworkCode.CSAP_2026.value}:99.9.9",
                "--actor",
                "officer-park",
            ]
        )
        == 1
    )
    invented = json.loads(capsys.readouterr().out)
    assert invented["status_code"] == 404
    assert cli_main(["policy", "author", "--title", "Bad", "--body", "Map", "--map", "nocolon", "--actor", "a"]) == 1
    assert json.loads(capsys.readouterr().out)["status_code"] == 400
    assert (
        cli_main(
            [
                "policy",
                "author",
                "--title",
                "Bad framework",
                "--body",
                "Map",
                "--map",
                "toy-catalog:10.2.1",
                "--actor",
                "a",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status_code"] == 400
    assert (
        cli_main(
            [
                "bind",
                "--framework",
                "",
                "--identifier",
                "10.2.1",
                "--title",
                "Empty framework",
                "--payload",
                "park@example.co.kr",
                "--actor",
                "officer-park",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status_code"] == 400
    assert _dispatch(Namespace(command="unknown")) == 2
    os.environ.setdefault("CWL_GRC_DATABASE_URL", f"sqlite:///{database}")
    assert _policy_command(Namespace(policy_command="unknown")) == 2
