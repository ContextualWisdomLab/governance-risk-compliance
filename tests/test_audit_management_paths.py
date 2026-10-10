"""Branch tests for audit-management paths not reached by the officer workflow tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cwl_grc import create_app
from cwl_grc.audit_management import (
    AuditWorkflowError,
    _get_referenced,
    select_sample_ordinals,
)
from cwl_grc.models import AuditProgram


def test_unknown_selection_method_is_rejected_with_a_next_action() -> None:
    """Reject an unknown sampling method and suggest seeded random selection."""
    with pytest.raises(AuditWorkflowError) as error:
        select_sample_ordinals("haphazard", 240, 25, None, None)
    assert error.value.status_code == 400
    assert "seeded_random" in error.value.next_action


def test_non_audit_validation_errors_keep_the_default_shape() -> None:
    """Keep non-audit validation errors at 422 with detail but no audit next action."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    response = client.post(
        "/policy-documents",
        headers={"X-Actor-Id": "policy-officer-kang", "X-Purpose": "policy_authoring"},
        json=["not", "an", "object"],
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"]
    assert "next_action" not in body


def test_purpose_is_checked_before_the_request_body() -> None:
    """An undeclared caller learns about the purpose first, not about the schema."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    missing = client.post("/audit-programs", json={"bogus": 1})
    assert missing.status_code == 401
    assert "audit_engagement" in missing.json()["next_action"]
    wrong = client.post(
        "/audit-programs",
        headers={"X-Actor-Id": "audit-planner-lee", "X-Purpose": "policy_authoring"},
        json={"bogus": 1},
    )
    assert wrong.status_code == 403
    assert wrong.json()["next_action"] == "Retry with X-Purpose: audit_engagement."
    remediation = client.post(
        "/remediation-actions/missing/completion",
        headers={"X-Actor-Id": "iam-engineer-yoon", "X-Purpose": "audit_engagement"},
        json={"bogus": 1},
    )
    assert remediation.status_code == 403
    assert "remediation_tracking" in remediation.json()["next_action"]
    declared = client.post(
        "/audit-programs",
        headers={"X-Actor-Id": "audit-planner-lee", "X-Purpose": "audit_engagement"},
        json={"bogus": 1},
    )
    assert declared.status_code == 422
    assert declared.json()["next_action"]


def test_missing_foreign_key_target_fails_loudly_even_without_asserts() -> None:
    """A corrupt store returns a 500 workflow error rather than a silent ``None``."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    with client.app.state.session_factory() as session:
        with pytest.raises(AuditWorkflowError) as error:
            _get_referenced(session, AuditProgram, "absent-program")
    assert error.value.status_code == 500
    assert "database integrity" in error.value.next_action
