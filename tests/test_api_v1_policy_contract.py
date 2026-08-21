"""Buyer-surface contract tests for the strict version-one policy API."""

from __future__ import annotations

import json

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from cwl_grc import create_app
from cwl_grc.app import (
    V1PolicyAuthorBody,
    _begin_idempotent_request,
    _problem_response,
    _request_digest,
)
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog import FrameworkCode
from cwl_grc.models import IdempotencyRecord
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
    empty = client.get("/v1/policy-documents")
    assert empty.status_code == 200
    assert empty.json()["items"] == []
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
    invalid_cursor = client.get(
        "/v1/policy-documents",
        params={"cursor": "secret-cursor-value"},
    )
    assert invalid_cursor.status_code == 400
    assert "secret-cursor-value" not in invalid_cursor.text
    assert invalid_cursor.json()["instance"] == "/v1/policy-documents"
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
    second = client.post(
        "/v1/policy-documents",
        headers=_headers("create-2"),
        json=_body("Second access policy"),
    )
    second_policy_id = second.json()["policy_document_id"]
    revision_body = {
        "policy_body": "The second edition adds quarterly access recertification.",
        "control_refs": [
            {
                "framework": FrameworkCode.ISMS_P_2023.value,
                "catalog_identifier": "2.5.1",
            }
        ],
    }
    first_etag = client.get(f"/v1/policy-documents/{policy_id}").headers["ETag"]
    second_etag = client.get(f"/v1/policy-documents/{second_policy_id}").headers["ETag"]
    first_shared = client.post(
        f"/v1/policy-documents/{policy_id}/versions",
        headers={**_headers("shared-revision"), "If-Match": first_etag},
        json=revision_body,
    )
    second_shared = client.post(
        f"/v1/policy-documents/{second_policy_id}/versions",
        headers={**_headers("shared-revision"), "If-Match": second_etag},
        json=revision_body,
    )
    assert first_shared.status_code == 201
    assert second_shared.status_code == 201
    assert first_shared.json()["policy_document_id"] == policy_id
    assert second_shared.json()["policy_document_id"] == second_policy_id
    assert first_shared.json()["current_version"]["version_number"] == 2
    assert second_shared.json()["current_version"]["version_number"] == 2
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
    assert revised.json()["current_version"]["version_number"] == 3
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


def test_v1_listing_batches_related_policy_queries() -> None:
    """Keep a page read bounded when several policies share mapped controls."""
    client = _client()
    for key in ("create-1", "create-2"):
        assert client.post(
            "/v1/policy-documents",
            headers=_headers(key),
            json=_body(key),
        ).status_code == 201
    statements: list[str] = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement.lower())

    event.listen(Engine, "before_cursor_execute", capture_statement)
    try:
        listed = client.get("/v1/policy-documents")
    finally:
        event.remove(Engine, "before_cursor_execute", capture_statement)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert sum("from policy_version" in statement for statement in statements) == 1
    assert sum("from policy_control_mapping" in statement for statement in statements) == 1
    assert sum("from control_item" in statement for statement in statements) == 1


def test_idempotency_reservation_handles_unique_insert_races() -> None:
    """Translate a concurrent unique-key collision into replay or safe retry."""
    body = V1PolicyAuthorBody.model_validate(_body())
    decision = AuthorizationDecision("officer-v1", PurposeCode.POLICY_AUTHORING)
    digest = _request_digest(body)

    class CollisionSession:
        """Minimal session double that reproduces a second-writer flush race."""

        def __init__(self, existing: IdempotencyRecord | None) -> None:
            self.existing = existing
            self.query_count = 0
            self.rolled_back = False

        def query(self, _model):
            return self

        def filter_by(self, **_filters):
            return self

        def one_or_none(self):
            self.query_count += 1
            return None if self.query_count == 1 else self.existing

        def add(self, _record) -> None:
            return None

        def flush(self) -> None:
            raise IntegrityError("INSERT", {}, RuntimeError("duplicate key"))

        def rollback(self) -> None:
            self.rolled_back = True

    def record_for(request_digest: str, status: int) -> IdempotencyRecord:
        payload = {
            "current_version": {
                "policy_version_id": "version-1",
                "version_number": 1,
                "policy_body": "body",
                "mapped_controls": [],
            }
        }
        return IdempotencyRecord(
            idempotency_record_id="record-1",
            actor_identifier="officer-v1",
            operation_name="operation",
            idempotency_key="key-1",
            request_digest=request_digest,
            response_status=status,
            response_payload=json.dumps(payload if status else {}),
            created_at=None,
        )

    for existing in (
        None,
        record_for("different", 0),
        record_for(digest, 0),
    ):
        session = CollisionSession(existing)
        with pytest.raises(HTTPException) as collision:
            _begin_idempotent_request(session, decision, "operation", "key-1", body)
        assert collision.value.status_code == 409
        assert session.rolled_back is True

    session = CollisionSession(record_for(digest, 201))
    record, replay = _begin_idempotent_request(session, decision, "operation", "key-1", body)
    assert record is None
    assert replay is not None
    assert replay.status_code == 201


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
    missing_policy_gaps = client.get(
        "/v1/policy-gaps",
        params={"policy_document_id": "missing"},
    )
    assert missing_policy_gaps.status_code == 404

    invalid = client.post(
        "/v1/policy-documents",
        headers=_headers("invalid-1"),
        json={
            **_body(),
            **{f"credential_secret_{index}": "must-not-echo" for index in range(6)},
        },
    )
    assert invalid.status_code == 422
    assert "must-not-echo" not in invalid.text
    assert all(f"credential_secret_{index}" not in invalid.text for index in range(6))
    assert invalid.json()["detail"].count(";") == 4
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
            "query_string": b"secret=do-not-reflect",
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
    assert response.body and b"do-not-reflect" not in response.body
