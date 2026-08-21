"""Evidence-request workflow tests with tenant and review-boundary coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from cwl_grc.app import create_app
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import create_evidence_record
from cwl_grc.evidence_requests import (
    create_evidence_request,
    next_action_for_evidence_request,
    submit_evidence_request,
)
from cwl_grc.models import EvidenceRequest


PERIOD_FROM = datetime(2026, 1, 1, tzinfo=timezone.utc)
PERIOD_TO = datetime(2026, 3, 31, tzinfo=timezone.utc)
DUE_AT = datetime(2026, 4, 15, tzinfo=timezone.utc)


def _headers(actor: str, purpose: str = "compliance_governance") -> dict[str, str]:
    """Return local-preview headers for one declared actor and purpose."""
    return {"X-Actor-Id": actor, "X-Purpose": purpose}


def _body(contributor: str = "contributor") -> dict[str, object]:
    """Return one realistic period- and scope-bound request body."""
    return {
        "request_title": "Quarterly privileged-access review",
        "requested_scope_type": "application",
        "requested_scope_reference": "billing-service",
        "requested_period_from": PERIOD_FROM.isoformat(),
        "requested_period_to": PERIOD_TO.isoformat(),
        "required_fields": ["reviewer", "decision_date", "population_digest"],
        "contributor_reference": contributor,
        "due_at": DUE_AT.isoformat(),
        "reuse_policy": "reusable",
    }


def test_evidence_request_http_lifecycle_preserves_audit_without_payload() -> None:
    """Create, submit, reject, and list a request without returning encrypted payload text."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))

    assert client.get("/evidence-requests").status_code == 200
    assert client.post("/evidence-requests", json=_body()).status_code == 401

    created = client.post(
        "/evidence-requests",
        headers=_headers("requester"),
        json=_body(),
    )
    assert created.status_code == 201
    request = created.json()
    request_id = request["evidence_request_id"]
    assert request["request_state"] == "requested"
    assert request["required_fields"] == ["reviewer", "decision_date", "population_digest"]
    assert request["audit_history"][0]["action_name"] == "create_evidence_request"
    assert "payload_text" not in request

    evidence = client.post(
        "/evidence-records",
        headers=_headers("contributor", "evidence_binding"),
        json={"evidence_title": "Access review", "payload_text": "Officer PII remains usable."},
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["evidence_record_id"]

    wrong_contributor = client.post(
        f"/evidence-requests/{request_id}/submissions",
        headers=_headers("other-contributor"),
        json={"evidence_record_id": evidence_id},
    )
    assert wrong_contributor.status_code == 403
    missing_evidence = client.post(
        f"/evidence-requests/{request_id}/submissions",
        headers=_headers("contributor"),
        json={"evidence_record_id": "missing-evidence"},
    )
    assert missing_evidence.status_code == 404

    submitted = client.post(
        f"/evidence-requests/{request_id}/submissions",
        headers=_headers("contributor"),
        json={"evidence_record_id": evidence_id},
    )
    assert submitted.status_code == 200
    assert submitted.json()["request_state"] == "submitted"
    assert len(submitted.json()["audit_history"]) == 2
    assert client.post(
        f"/evidence-requests/{request_id}/submissions",
        headers=_headers("contributor"),
        json={"evidence_record_id": evidence_id},
    ).status_code == 409

    same_actor_review = client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("contributor"),
        json={"decision_code": "accepted"},
    )
    assert same_actor_review.status_code == 403
    invalid_review = client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("reviewer"),
        json={"decision_code": "pending"},
    )
    assert invalid_review.status_code == 400
    missing_reason = client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("reviewer"),
        json={"decision_code": "rejected"},
    )
    assert missing_reason.status_code == 400
    rejected = client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("reviewer"),
        json={"decision_code": "rejected", "rejection_reason": "The period digest is missing."},
    )
    assert rejected.status_code == 200
    rejected_body = rejected.json()
    assert rejected_body["request_state"] == "rejected"
    assert rejected_body["rejection_reason"] == "The period digest is missing."
    assert len(rejected_body["audit_history"]) == 3
    assert client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("reviewer"),
        json={"decision_code": "accepted"},
    ).status_code == 409

    listed = client.get("/evidence-requests", headers=_headers("reader")).json()
    assert len(listed["evidence_requests"]) == 1
    assert listed["evidence_requests"][0]["next_action"].startswith("Request a corrected")


def test_accepted_request_is_visible_in_workspace_but_needs_no_action() -> None:
    """Accepted requests contribute to posture while remaining explicit and tenant-scoped."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    created = client.post(
        "/evidence-requests",
        headers=_headers("requester"),
        json=_body(),
    ).json()
    request_id = created["evidence_request_id"]
    evidence = client.post(
        "/evidence-records",
        headers=_headers("contributor", "evidence_binding"),
        json={"evidence_title": "Access review", "payload_text": "Evidence payload."},
    ).json()
    client.post(
        f"/evidence-requests/{request_id}/submissions",
        headers=_headers("contributor"),
        json={"evidence_record_id": evidence["evidence_record_id"]},
    )
    accepted = client.post(
        f"/evidence-requests/{request_id}/review",
        headers=_headers("reviewer"),
        json={"decision_code": "accepted"},
    )
    assert accepted.status_code == 200
    workspace = client.get("/compliance-workspace", headers=_headers("reader")).json()
    assert workspace["posture"]["evidence_request_state_counts"] == {
        "requested": 0,
        "submitted": 0,
        "accepted": 1,
        "rejected": 0,
    }
    assert workspace["evidence_requests"][0]["request_state"] == "accepted"
    assert not any(action["kind"] == "evidence_request" for action in workspace["next_actions"])
    assert "evidence_requests" not in workspace["not_yet_projected"]
    assert "payload_text" not in workspace["evidence_requests"][0]


def test_evidence_request_validation_and_tenant_boundary() -> None:
    """Reject malformed requests, cross-tenant evidence, and invalid direct state transitions."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_authorization_purposes(session)
        session.commit()
        decision = AuthorizationDecision("requester", PurposeCode.COMPLIANCE_GOVERNANCE, "tenant-a")
        valid = dict(
            request_title="Request",
            requested_scope_type="application",
            requested_scope_reference="billing",
            requested_period_from=PERIOD_FROM,
            requested_period_to=PERIOD_TO,
            required_fields=["reviewer"],
            contributor_reference="contributor",
            due_at=DUE_AT,
            reuse_policy="single_use",
        )
        with pytest.raises(HTTPException, match="request title"):
            create_evidence_request(session, decision, 1, **{key: value for key, value in valid.items() if key != "request_title"})
        with pytest.raises(HTTPException, match="Required evidence fields"):
            create_evidence_request(session, decision, **{**valid, "required_fields": ["reviewer", "reviewer"]})
        with pytest.raises(HTTPException, match="Use single_use"):
            create_evidence_request(session, decision, **{**valid, "reuse_policy": "share_everywhere"})
        with pytest.raises(HTTPException, match="period must be ordered"):
            create_evidence_request(
                session,
                decision,
                **{**valid, "requested_period_to": datetime(2025, 12, 31, tzinfo=timezone.utc)},
            )
        with pytest.raises(HTTPException, match="due date"):
            create_evidence_request(session, decision, **{**valid, "due_at": PERIOD_FROM})
        with pytest.raises(HTTPException, match="Required evidence fields"):
            create_evidence_request(session, decision, **{**valid, "required_fields": ["reviewer", 3]})
        with pytest.raises(HTTPException, match="required evidence field"):
            create_evidence_request(session, decision, **{**valid, "required_fields": []})
        with pytest.raises(HTTPException, match="request title"):
            create_evidence_request(session, decision, **{**valid, "request_title": 3})
        with pytest.raises(HTTPException, match="request title"):
            create_evidence_request(session, decision, **{**valid, "request_title": ""})
        with pytest.raises(HTTPException, match="not on file"):
            submit_evidence_request(session, decision, "missing-request", "missing-evidence")

        evidence = create_evidence_record(
            session,
            EvidenceCipher(None, allow_ephemeral=True),
            AuthorizationDecision("contributor", PurposeCode.EVIDENCE_BINDING, "tenant-b"),
            "Tenant B evidence",
            "Tenant B exact payload",
        )
        request = create_evidence_request(session, decision, **valid)
        create_evidence_request(
            session,
            decision,
            **{
                **valid,
                "requested_period_from": PERIOD_FROM.replace(tzinfo=None),
                "requested_period_to": PERIOD_TO.replace(tzinfo=None),
                "due_at": DUE_AT.replace(tzinfo=None),
            },
        )
        session.flush()
        with pytest.raises(HTTPException, match="not on file"):
            submit_evidence_request(
                session,
                AuthorizationDecision("contributor", PurposeCode.COMPLIANCE_GOVERNANCE, "tenant-a"),
                request.evidence_request_id,
                evidence.evidence_record_id,
            )
        with pytest.raises(DBAPIError):
            session.query(EvidenceRequest).filter_by(evidence_request_id=request.evidence_request_id).update(
                {"request_state": "accepted"}, synchronize_session=False
            )
        session.rollback()

    assert next_action_for_evidence_request("future") == "Review the evidence request state before proceeding."
