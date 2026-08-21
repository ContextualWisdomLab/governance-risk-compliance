"""Buyer-surface contract tests for the strict version-one policy API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request

from cwl_grc import create_app
from cwl_grc.app import _problem_response
from cwl_grc.catalog import FrameworkCode
from cwl_grc.policy import encode_page_cursor


def _client() -> TestClient:
    """Return an isolated version-one API client."""
    return TestClient(create_app(database_url="sqlite://", evidence_key=None))


def _headers(key: str | None = None) -> dict[str, str]:
    """Return local preview policy-authoring headers."""
    headers = {"X-Actor-Id": "officer-v1", "X-Purpose": "policy_authoring"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _body(title: str = "Access policy") -> dict[str, object]:
    """Return a realistic policy request using official catalog identifiers."""
    return {
        "policy_title": title,
        "policy_body": "Unique accounts, least privilege, and formal access removal.",
        "control_refs": [
            {
                "framework": FrameworkCode.CSAP_2026.value,
                "catalog_identifier": "10.2.1",
            },
            {
                "framework": FrameworkCode.SOC2_TSC_2017.value,
                "catalog_identifier": "CC6.1",
            },
        ],
    }


def test_v1_authoring_is_strict_bounded_and_idempotent() -> None:
    """Create, replay, reject key reuse, paginate, and expose an ETag."""
    client = _client()
    missing_key = client.post("/v1/policy-documents", headers=_headers(), json=_body())
    assert missing_key.status_code == 422
    assert missing_key.headers["content-type"].startswith("application/problem+json")
    assert missing_key.json()["status"] == 422
    assert client.post(
        "/v1/policy-documents",
        headers=_headers(" "),
        json=_body(),
    ).status_code == 400
    assert client.post(
        "/v1/policy-documents",
        headers=_headers("x" * 256),
        json=_body(),
    ).status_code == 400

    created = client.post(
        "/v1/policy-documents",
        headers=_headers("create-1"),
        json=_body(),
    )
    assert created.status_code == 201
    assert created.headers["ETag"].startswith('"')
    payload = created.json()
    replay = client.post(
        "/v1/policy-documents",
        headers=_headers("create-1"),
        json=_body(),
    )
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == payload
    conflict = client.post(
        "/v1/policy-documents",
        headers=_headers("create-1"),
        json=_body("different request"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["type"].endswith("/conflict")

    second = client.post(
        "/v1/policy-documents",
        headers=_headers("create-2"),
        json=_body("Second access policy"),
    )
    assert second.status_code == 201
    listed = client.get("/v1/policy-documents", params={"limit": 1})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
    cursor = listed.json()["next_cursor"]
    assert cursor
    next_page = client.get("/v1/policy-documents", params={"limit": 1, "cursor": cursor})
    assert next_page.status_code == 200
    assert len(next_page.json()["items"]) == 1
    assert client.get("/v1/policy-documents", params={"cursor": "not-a-cursor"}).status_code == 400
    assert client.get(
        "/v1/policy-documents",
        params={"cursor": encode_page_cursor("only-one-part")},
    ).status_code == 400
    assert client.get(
        "/v1/policy-documents",
        params={"cursor": encode_page_cursor("not-a-date", "policy")},
    ).status_code == 400
    assert client.get("/v1/policy-documents/missing").status_code == 404


def test_v1_revision_requires_current_etag_and_replays() -> None:
    """Require a precondition, publish an edition, and replay it safely."""
    client = _client()
    created = client.post(
        "/v1/policy-documents",
        headers=_headers("create-1"),
        json=_body(),
    )
    policy_id = created.json()["policy_document_id"]
    revision_body = {
        "policy_body": "The second edition adds quarterly access recertification.",
        "control_refs": [
            {
                "framework": FrameworkCode.ISMS_P_2023.value,
                "catalog_identifier": "2.5.1",
            }
        ],
    }
    missing = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers=_headers("rev-1"),
        json=revision_body,
    )
    assert missing.status_code == 428
    stale = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers={**_headers("rev-2"), "If-Match": '"stale"'},
        json=revision_body,
    )
    assert stale.status_code == 412
    current = client.get(f"/v1/policy-documents/{policy_id}")
    etag = current.headers["ETag"]
    revised = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers={**_headers("rev-3"), "If-Match": etag},
        json=revision_body,
    )
    assert revised.status_code == 201
    assert revised.json()["current_version"]["version_number"] == 2
    replay = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers={**_headers("rev-3"), "If-Match": '"stale"'},
        json=revision_body,
    )
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    wildcard = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers={**_headers("rev-4"), "If-Match": "*"},
        json={**revision_body, "policy_body": "The third edition adds owner review."},
    )
    assert wildcard.status_code == 201
    missing_policy = client.post(
        "/v1/policy-documents/missing/versions",
        headers={**_headers("missing-revision"), "If-Match": "*"},
        json=revision_body,
    )
    assert missing_policy.status_code == 404


def test_v1_gaps_validation_and_openapi_contract() -> None:
    """Expose paged gaps and safe RFC 9457 errors for malformed input."""
    client = _client()
    created = client.post(
        "/v1/policy-documents",
        headers=_headers("create-1"),
        json=_body(),
    )
    policy_id = created.json()["policy_document_id"]
    gaps = client.get(
        "/v1/policy-gaps",
        params={"policy_document_id": policy_id, "limit": 1},
    )
    assert gaps.status_code == 200
    assert len(gaps.json()["items"]) == 1
    cursor = gaps.json()["next_cursor"]
    assert cursor
    next_gaps = client.get(
        "/v1/policy-gaps",
        params={"policy_document_id": policy_id, "limit": 1, "cursor": cursor},
    )
    assert next_gaps.status_code == 200
    assert len(next_gaps.json()["items"]) == 1
    assert client.get("/v1/policy-gaps", params={"cursor": "bad"}).status_code == 400
    assert client.get(
        "/v1/policy-gaps",
        params={"cursor": encode_page_cursor("not-a-date", "policy", "framework", "id")},
    ).status_code == 400

    invalid = client.post(
        "/v1/policy-documents",
        headers=_headers("invalid-1"),
        json={**_body(), "credential_secret": "must-not-echo", "unknown": True},
    )
    assert invalid.status_code == 422
    assert "must-not-echo" not in invalid.text
    unauthorized = client.post(
        "/v1/policy-documents",
        headers={"Idempotency-Key": "auth-1"},
        json=_body(),
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["type"].endswith("/unauthorized")
    assert client.post("/officer/policy").status_code == 422
    docs = client.get("/openapi.json").json()
    assert docs["paths"]["/v1/policy-documents"]["post"]["requestBody"]
    assert any(
        parameter["name"] == "idempotency-key" and parameter["required"]
        for parameter in docs["paths"]["/v1/policy-documents"]["post"]["parameters"]
    )
    assert docs["paths"]["/policy-documents"]["post"]["deprecated"] is True


def test_problem_builder_preserves_safe_headers_and_custom_type() -> None:
    """The problem builder keeps correlation metadata without reflecting input."""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/test",
            "raw_path": b"/v1/test",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "root_path": "",
        }
    )
    response = _problem_response(
        request,
        418,
        "short detail",
        code="teapot",
        headers={"Retry-After": "0"},
    )
    assert response.status_code == 418
    assert response.headers["Retry-After"] == "0"
    assert response.media_type == "application/problem+json"
