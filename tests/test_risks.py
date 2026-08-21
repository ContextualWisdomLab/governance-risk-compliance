"""Real risk-register workflows with immutable assessment and control evidence links."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from cwl_grc.app import create_app
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.database import create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.internal_controls import (
    create_control_foundation,
    create_control_test_plan,
    record_control_test_execution,
    record_control_test_result,
    record_evidence_usage,
)
from cwl_grc.models import EvidenceRecord, RiskAssessment, RiskMethodology
from cwl_grc.risks import (
    _validated_control_links,
    assess_risk,
    create_risk_methodology,
    create_risk_register,
    latest_risk_assessment,
    list_risk_register,
    next_action_for_risk,
)


JANUARY_START = datetime(2026, 1, 1)
JANUARY_END = datetime(2026, 1, 31)
FUTURE_REVIEW = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _factory():  # noqa: ANN202
    """Return one real SQLite product store with catalog purposes seeded."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_authorization_purposes(session)
        session.commit()
    return factory


def _decision(purpose: PurposeCode = PurposeCode.COMPLIANCE_GOVERNANCE, tenant: str = "local_development"):
    """Return one exact-tenant authorization decision."""
    return AuthorizationDecision("risk-officer", purpose, tenant)


def _methodology(session, decision, *, appetite: int = 10, factor: int = 50):  # noqa: ANN001
    """Create the deterministic methodology used by risk tests."""
    return create_risk_methodology(
        session,
        decision,
        "CWL-5X5",
        1,
        "CWL five by five risk method",
        5,
        5,
        factor,
        appetite,
        appetite + 10,
    )


def _risk(session, decision, code: str = "RISK-ACCESS-001"):  # noqa: ANN001
    """Create one realistic access-governance risk."""
    return create_risk_register(
        session,
        decision,
        code,
        "Privileged access remains active after role change",
        "A role change is not reconciled to privileged access within the review period.",
        "access",
        "risk-register-interview-2026-01",
        "application",
        "identity-service",
        "access-owner",
        30,
    )


def _control_link(session, control_decision, *, design: bool = False):  # noqa: ANN001
    """Create a real implemented control, completed test, and supporting evidence usage."""
    foundation = create_control_foundation(
        session,
        control_decision,
        objective_code=f"OBJ-{uuid4().hex[:8]}",
        objective_title="Logical access governance",
        objective_statement="Access is reviewed against approved role changes.",
        control_code=f"IC-{uuid4().hex[:8]}",
        control_name="Role-change access review",
        control_statement="Review privileged access after role changes.",
        control_type="detective",
        execution_mode="manual",
        frequency="monthly",
        expected_evidence="Approved access review register",
        scope_type="application",
        scope_reference="identity-service",
        owner_reference="access-owner",
        effective_from=JANUARY_START,
    )
    plan = create_control_test_plan(
        session,
        control_decision,
        foundation.definition_version.control_definition_version_id,
        foundation.implementation.control_implementation_id,
        "Design review" if design else "Operating review",
        "design" if design else "operating",
        "Inspect approved access review evidence.",
        "January role changes",
        "monthly",
    )
    execution = record_control_test_execution(
        session,
        control_decision,
        plan.test_plan_id,
        JANUARY_START,
        JANUARY_END,
        "Five role changes",
        "The sampled role changes were reconciled.",
    )
    result = record_control_test_result(
        session,
        control_decision,
        execution.test_execution_id,
        "effective",
        "The sampled access review was effective.",
    )
    encrypted = EvidenceCipher(None, allow_ephemeral=True).encrypt("Exact access review register")
    evidence = EvidenceRecord(
        evidence_record_id=uuid4().hex,
        tenant_id=control_decision.tenant_id,
        evidence_title="January access review register",
        collector_actor=control_decision.actor_identifier,
        purpose_code=PurposeCode.EVIDENCE_BINDING.value,
        ciphertext_payload=encrypted,
        collected_at=datetime(2026, 1, 15),
    )
    session.add(evidence)
    session.flush()
    usage = record_evidence_usage(
        session,
        AuthorizationDecision(
            control_decision.actor_identifier,
            PurposeCode.EVIDENCE_BINDING,
            control_decision.tenant_id,
        ),
        evidence.evidence_record_id,
        execution.test_execution_id,
        "supporting",
        "Evidence supports the completed control test.",
    )
    return foundation, result, usage


def _headers(actor: str, purpose: str = "compliance_governance") -> dict[str, str]:
    """Return local-preview actor and purpose headers."""
    return {"X-Actor-Id": actor, "X-Purpose": purpose}


def test_risk_methodology_register_and_immutable_assessment_lifecycle() -> None:
    """Calculate inherent and residual scores from real internal control evidence usage."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        methodology = _methodology(session, decision, appetite=5)
        risk = _risk(session, decision)
        with pytest.raises(HTTPException, match="already exists"):
            _risk(session, decision)
        control = _control_link(session, _decision(PurposeCode.COVERAGE_REVIEW))
        assessment = assess_risk(
            session,
            decision,
            risk.risk_id,
            methodology.methodology_id,
            3,
            5,
            "The access review is the current mitigating control.",
            FUTURE_REVIEW,
            [
                {
                    "control_implementation_id": control[0].implementation.control_implementation_id,
                    "control_test_result_id": control[1].test_result_id,
                    "evidence_usage_id": control[2].evidence_usage_id,
                }
            ],
            expected_revision_number=1,
            decision_reference="risk-committee-minutes-2026-01",
        )
        assert assessment.inherent_score == 15
        assert assessment.residual_score == 8
        assert assessment.appetite_status == "above_appetite"
        assert risk.revision_number == 2
        assert latest_risk_assessment(session, decision, risk.risk_id) is assessment
        assert list_risk_register(session, decision) == [risk]
        assert next_action_for_risk(risk, assessment).startswith("Create a versioned")
        with pytest.raises(HTTPException, match="changed"):
            assess_risk(
                session,
                decision,
                risk.risk_id,
                methodology.methodology_id,
                3,
                3,
                "Stale revision.",
                FUTURE_REVIEW,
                [],
                expected_revision_number=1,
            )
        session.commit()
        with pytest.raises(DBAPIError):
            session.query(RiskAssessment).filter_by(risk_assessment_id=assessment.risk_assessment_id).update(
                {RiskAssessment.assessment_rationale: "tampered"}, synchronize_session=False
            )
        session.rollback()
        with pytest.raises(DBAPIError):
            session.query(RiskMethodology).filter_by(methodology_id=methodology.methodology_id).delete(
                synchronize_session=False
            )


def test_risk_http_workspace_and_input_boundaries() -> None:
    """Expose the buyer slice through local routes while keeping writes purpose-bound."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    assert client.post("/risk-methodologies", json={}).status_code == 401
    headers = _headers("methodology-owner")
    methodology = client.post(
        "/risk-methodologies",
        headers=headers,
        json={
            "methodology_code": "CWL-5X5",
            "methodology_version": 1,
            "methodology_title": "Five by five",
            "likelihood_scale_max": 5,
            "impact_scale_max": 5,
            "effective_control_factor_percent": 50,
            "appetite_threshold": 8,
            "tolerance_threshold": 18,
        },
    )
    assert methodology.status_code == 201
    risk = client.post(
        "/risks",
        headers=headers,
        json={
            "risk_code": "RISK-ACCESS-001",
            "risk_title": "Access risk",
            "risk_scenario": "Access remains after role change.",
            "risk_category": "access",
            "source_reference": "interview-2026-01",
            "affected_scope_type": "application",
            "affected_scope_reference": "identity-service",
            "owner_reference": "access-owner",
            "review_cadence_days": 30,
        },
    )
    assert risk.status_code == 201
    listed = client.get("/risks", headers=_headers("reader")).json()
    assert listed["risks"][0]["assessment"] is None
    assessment = client.post(
        f"/risks/{risk.json()['risk_id']}/assessments",
        headers=headers,
        json={
            "methodology_id": methodology.json()["methodology_id"],
            "likelihood": 3,
            "impact": 3,
            "assessment_rationale": "No tested mitigation is attached yet.",
            "next_review_at": FUTURE_REVIEW.isoformat(),
            "expected_revision_number": 1,
            "control_links": [],
        },
    )
    assert assessment.status_code == 201
    assert assessment.json()["residual_score"] == 9
    workspace = client.get("/compliance-workspace", headers=_headers("reader")).json()
    assert workspace["projection"].endswith("_risks")
    assert workspace["posture"]["risk_total"] == 1
    assert workspace["risks"][0]["assessment"]["appetite_status"] == "above_appetite"
    assert "risk_register" not in workspace["not_yet_projected"]
    assert "risk_treatments" in workspace["not_yet_projected"]


def test_risk_validation_and_tenant_boundaries() -> None:
    """Reject malformed methodology, assessment, direct catalog semantics, and foreign tenants."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        with pytest.raises(HTTPException, match="methodology code"):
            create_risk_methodology(session, decision, "", 1, "Bad", 5, 5, 50, 10, 20)
        methodology = _methodology(session, decision)
        with pytest.raises(HTTPException, match="already exists"):
            _methodology(session, decision)
        with pytest.raises(HTTPException, match="outside"):
            create_risk_methodology(session, decision, "BAD", 2, "Bad", 1, 5, 50, 10, 20)
        with pytest.raises(HTTPException, match="positive"):
            create_risk_methodology(session, decision, "BAD", 0, "Bad", 5, 5, 50, 10, 20)
        with pytest.raises(HTTPException, match="tolerance"):
            create_risk_methodology(session, decision, "BAD", 2, "Bad", 5, 5, 50, 10, 9)
        risk = _risk(session, decision)
        with pytest.raises(HTTPException, match="positive"):
            create_risk_register(session, decision, "BAD", "title", "scenario", "category", "source", "app", "ref", "owner", 0)
        with pytest.raises(HTTPException, match="Control links"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, None, expected_revision_number=1)
        with pytest.raises(HTTPException, match="Control links"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, {}, expected_revision_number=1)
        with pytest.raises(HTTPException, match="object"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, ["bad"], expected_revision_number=1)
        with pytest.raises(HTTPException, match="control implementation"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, [{}], expected_revision_number=1)
        with pytest.raises(HTTPException, match="not on file"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, [{"control_implementation_id": "i", "control_test_result_id": "r", "evidence_usage_id": "u"}], expected_revision_number=1)
        with pytest.raises(HTTPException, match="outside"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 0, 3, "reason", FUTURE_REVIEW, [], expected_revision_number=1)
        with pytest.raises(HTTPException, match="outside"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 6, 3, "reason", FUTURE_REVIEW, [], expected_revision_number=1)
        with pytest.raises(HTTPException, match="not on file"):
            assess_risk(session, decision, risk.risk_id, "missing-methodology", 3, 3, "reason", FUTURE_REVIEW, [], expected_revision_number=1)
        foreign = _decision(tenant="tenant-b")
        with pytest.raises(HTTPException, match="not on file"):
            assess_risk(session, foreign, risk.risk_id, methodology.methodology_id, 3, 3, "reason", FUTURE_REVIEW, [], expected_revision_number=1)
        with pytest.raises(HTTPException, match="compliance_governance"):
            create_risk_register(session, _decision(PurposeCode.COVERAGE_REVIEW), "BAD", "title", "scenario", "category", "source", "app", "ref", "owner", 30)


def test_risk_next_actions_and_invalid_control_links() -> None:
    """Keep overdue, empty, duplicate, and non-mitigating control links explicit."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        methodology = _methodology(session, decision)
        risk = _risk(session, decision, "RISK-EMPTY-001")
        assert next_action_for_risk(risk, None).startswith("Record an inherent")
        risk.next_review_at = datetime(2020, 1, 1)
        assert next_action_for_risk(risk, None).startswith("Review this overdue")
        risk.next_review_at = datetime(2027, 1, 1)
        assert next_action_for_risk(risk, None, current=datetime(2026, 1, 1)).startswith("Record an inherent")
        first = _control_link(session, _decision(PurposeCode.COVERAGE_REVIEW), design=True)
        link = {
            "control_implementation_id": first[0].implementation.control_implementation_id,
            "control_test_result_id": first[1].test_result_id,
            "evidence_usage_id": first[2].evidence_usage_id,
        }
        with pytest.raises(HTTPException, match="once"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 2, 2, "Duplicate link.", FUTURE_REVIEW, [link, link], expected_revision_number=1)
        first[0].implementation.implementation_status = "planned"
        with pytest.raises(HTTPException, match="implemented"):
            assess_risk(session, decision, risk.risk_id, methodology.methodology_id, 2, 2, "Not implemented.", FUTURE_REVIEW, [link], expected_revision_number=1)


def test_risk_normal_and_closed_next_actions() -> None:
    """Keep normal monitoring and closed-history actions explicit."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        methodology = _methodology(session, decision, appetite=20)
        risk = _risk(session, decision, "RISK-CLOSED-001")
        assessment = assess_risk(
            session,
            decision,
            risk.risk_id,
            methodology.methodology_id,
            2,
            2,
            "Within appetite.",
            FUTURE_REVIEW,
            [],
            expected_revision_number=1,
        )
        assert next_action_for_risk(risk, assessment).startswith("Monitor")
        risk.risk_status = "closed"
        assert next_action_for_risk(risk, assessment).startswith("Retain")


def test_risk_control_link_defensive_relationship_guards() -> None:
    """Keep malformed historical relationship chains fail-closed."""
    implementation = SimpleNamespace(control_implementation_id="implementation", implementation_status="implemented")
    result = SimpleNamespace(test_result_id="result", test_execution_id="execution", result_code="effective")
    usage = SimpleNamespace(
        evidence_usage_id="usage",
        control_implementation_id="implementation",
        control_test_execution_id="execution",
        usage_status="supporting",
    )
    execution = SimpleNamespace(
        control_implementation_id="implementation",
        test_execution_id="execution",
        test_plan_id="plan",
        execution_status="completed",
    )
    plan = SimpleNamespace(effectiveness_type="operating")

    def fake_session(*results):  # noqa: ANN202
        session = Mock()
        queries = []
        for result_value in results:
            query = Mock()
            query.filter_by.return_value.one_or_none.return_value = result_value
            queries.append(query)
        session.query.side_effect = queries
        return session

    link = {"control_implementation_id": "implementation", "control_test_result_id": "result", "evidence_usage_id": "usage"}
    with pytest.raises(HTTPException, match="not for the linked implementation"):
        _validated_control_links(fake_session(implementation, result, usage, None), _decision(), [link], 50)
    usage.control_implementation_id = "other"
    with pytest.raises(HTTPException, match="not for the linked implementation"):
        _validated_control_links(fake_session(implementation, result, usage, execution), _decision(), [link], 50)
    usage.control_implementation_id = "implementation"
    usage.control_test_execution_id = "other"
    with pytest.raises(HTTPException, match="test result execution"):
        _validated_control_links(fake_session(implementation, result, usage, execution), _decision(), [link], 50)
    usage.control_test_execution_id = "execution"
    with pytest.raises(HTTPException, match="plan"):
        _validated_control_links(fake_session(implementation, result, usage, execution, None), _decision(), [link], 50)
    assert _validated_control_links(fake_session(implementation, result, usage, execution, plan), _decision(), [link], 50)[0][0] == 50
