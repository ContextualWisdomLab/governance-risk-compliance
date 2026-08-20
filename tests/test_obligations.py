"""Real obligation-register and applicability workflows."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from cwl_grc.app import create_app
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, seed_control_catalog
from cwl_grc.database import create_session_factory
from cwl_grc.internal_controls import create_control_foundation
from cwl_grc.models import (
    ApplicabilityDecision,
    ChangeImpactAssessment,
    ControlItem,
    ObligationRequirement,
    PolicyDocument,
    PolicyVersion,
    RegulatorySource,
    SourceRevision,
)
from cwl_grc.keyverse_authentication import (
    KeyverseAccessTokenSettings,
    KeyverseAccessTokenVerifier,
    parse_keyverse_jwks,
)
from cwl_grc.obligations import (
    ApplicabilityCode,
    ImpactCode,
    ReapprovalCode,
    add_legal_interpretation,
    assess_change_impact,
    assign_obligation_owner,
    create_applicability_rule,
    create_compliance_obligation,
    create_jurisdiction,
    create_regulatory_source,
    create_source_revision,
    decide_applicability,
    link_obligation_requirement,
    list_obligation_worklist,
    obligation_next_action,
    record_regulatory_change,
    register_compliance_commitment,
)
from cwl_grc.policy import ControlRef, author_policy


JANUARY = datetime(2026, 1, 1)
FEBRUARY = datetime(2026, 2, 1)
MARCH = datetime(2026, 3, 1)
AUTH_NOW = datetime(2026, 8, 19, 13, 30, tzinfo=timezone.utc)
AUTH_ISSUER = "https://identity.example.test/realms/cwl"


def _factory():  # noqa: ANN202
    """Return a seeded real SQLite product store."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()
    return factory


def _decision(
    purpose: PurposeCode = PurposeCode.COMPLIANCE_GOVERNANCE,
    tenant_id: str = "local_development",
) -> AuthorizationDecision:
    """Return one deterministic compliance officer decision."""
    return AuthorizationDecision("compliance-officer", purpose, tenant_id)


def _source(session, decision):  # noqa: ANN001
    """Create one official source and an exact first edition."""
    source = create_regulatory_source(
        session,
        decision,
        "EU-DORA",
        "regulation",
        "Digital operational resilience reference",
        "European Union",
        "https://example.test/dora",
        "identifier_only",
        source_artifact_reference="artifact://dora-1",
    )
    revision = create_source_revision(
        session,
        decision,
        source.regulatory_source_id,
        1,
        JANUARY,
        FEBRUARY,
        "sha256:dora-v1",
        "Initial published edition",
        immutable_artifact_reference="artifact://dora-v1",
    )
    return source, revision


def _obligation(session, decision, revision):  # noqa: ANN001
    """Create one jurisdiction-scoped regulatory obligation."""
    jurisdiction = create_jurisdiction(
        session,
        decision,
        "EU",
        "European Union",
        "regional",
        "https://example.test/eu",
    )
    return create_compliance_obligation(
        session,
        decision,
        revision.source_revision_id,
        "DORA-ICT-01",
        "ICT resilience governance",
        "Maintain a documented and tested ICT resilience program.",
        "regulatory",
        "organization",
        "tenant-1",
        FEBRUARY,
        jurisdiction_id=jurisdiction.jurisdiction_id,
    )


def _protected_client() -> tuple[TestClient, Any]:
    """Return a Keyverse-protected client and its signing key."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "obligation-key", "use": "sig", "alg": "RS256"})
    verifier = KeyverseAccessTokenVerifier(
        KeyverseAccessTokenSettings(
            issuer=AUTH_ISSUER,
            audience="cwl-grc-api",
            allowed_client_ids=frozenset({"cwl-grc-web"}),
            allowed_roles=frozenset({"compliance_officer"}),
        ),
        parse_keyverse_jwks(json.dumps({"keys": [public_jwk]}).encode()),
        now=lambda: AUTH_NOW,
    )
    return TestClient(create_app(database_url="sqlite://", evidence_key=None, access_token_verifier=verifier)), private_key


def _protected_token(private_key: Any, scope: str = "grc.compliance.read") -> str:
    """Sign one valid compliance-read access token for the protected route."""
    return jwt.encode(
        {
            "iss": AUTH_ISSUER,
            "sub": "keyverse-compliance-officer",
            "aud": "cwl-grc-api",
            "exp": int((AUTH_NOW + timedelta(minutes=5)).timestamp()),
            "nbf": int((AUTH_NOW - timedelta(seconds=1)).timestamp()),
            "iat": int((AUTH_NOW - timedelta(seconds=1)).timestamp()),
            "jti": "obligation-route-token",
            "client_id": "cwl-grc-web",
            "scope": scope,
            "role": "compliance_officer",
            "org": "tenant-1",
            "workspace": "workspace-1",
            "principal_kind": "human",
        },
        private_key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "obligation-key"},
    )


def test_obligation_lifecycle_preserves_applicability_and_change_history() -> None:
    """A source, obligation, decision, mapping, and change form one traceable workflow."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        source, revision = _source(session, decision)
        obligation = _obligation(session, decision, revision)
        rule = create_applicability_rule(
            session,
            decision,
            obligation.compliance_obligation_id,
            "EU scope rule",
            "jurisdiction == EU and service == ICT",
        )
        not_applicable = decide_applicability(
            session,
            decision,
            obligation.compliance_obligation_id,
            ApplicabilityCode.NOT_APPLICABLE.value,
            "organization",
            "tenant-1",
            "The service is outside this legal scope for the first review period.",
            "evidence://legal-review-1",
            FEBRUARY,
            MARCH,
            applicability_rule_id=rule.applicability_rule_id,
        )
        applicable = decide_applicability(
            session,
            decision,
            obligation.compliance_obligation_id,
            ApplicabilityCode.APPLICABLE.value,
            "organization",
            "tenant-1",
            "The tenant now operates the in-scope service.",
            "evidence://legal-review-2",
            MARCH,
            MARCH,
            supersedes_decision_id=not_applicable.applicability_decision_id,
        )
        interpretation = add_legal_interpretation(
            session,
            decision,
            obligation.compliance_obligation_id,
            "The officer records the source interpretation for review.",
            "legal-memo://dora-1",
        )
        commitment = register_compliance_commitment(
            session,
            decision,
            obligation.compliance_obligation_id,
            "CUSTOMER-DORA-1",
            "Customer resilience commitment",
            "contract",
            "customer-contract-1",
            FEBRUARY,
            effective_to=datetime(2027, 1, 1),
        )
        owner = assign_obligation_owner(
            session,
            decision,
            obligation.compliance_obligation_id,
            "accountable",
            "orgmetra:resilience-owner",
            FEBRUARY,
        )
        policy = author_policy(
            session,
            AuthorizationDecision("policy-officer", PurposeCode.POLICY_AUTHORING),
            "ICT resilience policy",
            "The organization tests ICT resilience.",
            [ControlRef(FrameworkCode.CSAP_2026, "10.2.1")],
        )
        policy_version_id = policy.policy_versions[0].policy_version_id
        requirement = link_obligation_requirement(
            session,
            decision,
            obligation.compliance_obligation_id,
            "DORA-REQ-1",
            "Resilience policy requirement",
            "The approved policy addresses the source obligation.",
            policy_version_id=policy_version_id,
            control_item_id=session.query(ControlItem).first().control_item_id,
            source_locator="article-1",
        )
        with pytest.raises(HTTPException, match="target already exists"):
            link_obligation_requirement(
                session,
                decision,
                obligation.compliance_obligation_id,
                "DORA-REQ-1-DUPLICATE",
                "Duplicate resilience policy requirement",
                "The same policy target cannot be linked twice.",
                policy_version_id=policy_version_id,
            )
        change = record_regulatory_change(
            session,
            decision,
            revision.source_revision_id,
            "DORA-CHANGE-1",
            "The source publisher issued a changed edition.",
            "diff://dora-v1-v2",
            effective_at=datetime(2026, 6, 1),
        )
        assessment = assess_change_impact(
            session,
            decision,
            change.regulatory_change_id,
            obligation.compliance_obligation_id,
            ImpactCode.POLICY_UPDATE.value,
            "The policy needs a new approval cycle.",
            "policy-owner",
            "Revise and reapprove the policy before the effective date.",
            ReapprovalCode.REQUIRED.value,
            due_at=datetime(2026, 12, 1),
        )
        assert source.source_artifact_reference == "artifact://dora-1"
        assert revision.content_digest == "sha256:dora-v1"
        assert applicable.supersedes_decision_id == not_applicable.applicability_decision_id
        assert interpretation.interpretation_number == 1
        assert commitment.commitment_type == "contract"
        assert owner.owner_reference == "orgmetra:resilience-owner"
        assert requirement.review_status == "proposed"
        assert assessment.reapproval_status == ReapprovalCode.REQUIRED.value
        assert [item.queue for item in list_obligation_worklist(session, decision, as_of=FEBRUARY)] == ["upcoming"]
        assert list_obligation_worklist(session, decision, as_of=datetime(2026, 5, 1))[0].queue == "overdue"


def test_obligation_requirement_target_is_unique_when_optional_targets_are_null() -> None:
    """The database rejects duplicate policy targets despite nullable columns."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        _source_row, revision = _source(session, decision)
        obligation = _obligation(session, decision, revision)
        policy = author_policy(
            session,
            AuthorizationDecision("policy-officer", PurposeCode.POLICY_AUTHORING),
            "Unique target policy",
            "The organization maintains a unique obligation target.",
            [],
        )
        policy_version_id = policy.policy_versions[0].policy_version_id
        link_obligation_requirement(
            session,
            decision,
            obligation.compliance_obligation_id,
            "UNIQUE-REQ-1",
            "Unique requirement",
            "The target is linked once.",
            policy_version_id=policy_version_id,
        )
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    ObligationRequirement(
                        obligation_requirement_id="duplicate-target",
                        tenant_id=decision.tenant_id,
                        compliance_obligation_id=obligation.compliance_obligation_id,
                        policy_version_id=policy_version_id,
                        requirement_code="UNIQUE-REQ-2",
                        requirement_title="Duplicate requirement",
                        review_status="proposed",
                        mapping_rationale="The database must reject this duplicate target.",
                        created_at=FEBRUARY,
                    )
                )
                session.flush()
        with pytest.raises(DBAPIError, match="start proposed"):
            with session.begin_nested():
                session.add(
                    ObligationRequirement(
                        obligation_requirement_id="self-approved-target",
                        tenant_id=decision.tenant_id,
                        compliance_obligation_id=obligation.compliance_obligation_id,
                        policy_version_id=policy_version_id,
                        requirement_code="UNIQUE-REQ-3",
                        requirement_title="Self-approved requirement",
                        review_status="approved",
                        mapping_rationale="The database must reject self-asserted approval.",
                        created_at=FEBRUARY,
                    )
                )
                session.flush()


def test_obligation_can_link_internal_control_and_worklist_unknown() -> None:
    """An applicable obligation can point to a reviewed internal control without duplicating catalog data."""
    factory = _factory()
    compliance = _decision()
    with factory() as session:
        _source_row, revision = _source(session, compliance)
        obligation = _obligation(session, compliance, revision)
        foundation = create_control_foundation(
            session,
            _decision(PurposeCode.COVERAGE_REVIEW),
            objective_code="OBJ-RESILIENCE",
            objective_title="Resilience objective",
            objective_statement="Resilience controls operate as designed.",
            control_code="IC-RESILIENCE-1",
            control_name="Resilience testing",
            control_statement="Test the resilience procedure.",
            control_type="detective",
            execution_mode="manual",
            frequency="quarterly",
            expected_evidence="Resilience test report",
            scope_type="organization",
            scope_reference="tenant-1",
            owner_reference="resilience-owner",
            effective_from=FEBRUARY,
        )
        requirement = link_obligation_requirement(
            session,
            compliance,
            obligation.compliance_obligation_id,
            "DORA-REQ-2",
            "Resilience control requirement",
            "The internal control is the organization-designed response.",
            internal_control_definition_id=foundation.definition.internal_control_definition_id,
            control_implementation_id=foundation.implementation.control_implementation_id,
        )
        assert requirement.internal_control_definition_id == foundation.definition.internal_control_definition_id
        unknown = list_obligation_worklist(session, compliance, as_of=JANUARY)
        assert unknown[0].applicability_code == "unknown"
        decide_applicability(
            session,
            compliance,
            obligation.compliance_obligation_id,
            "pending_review",
            "organization",
            "tenant-1",
            "The organization scope needs review.",
            "evidence://tenant-1",
            FEBRUARY,
            MARCH,
        )
        decide_applicability(
            session,
            compliance,
            obligation.compliance_obligation_id,
            "partially_applicable",
            "application",
            "app-1",
            "Only one application is in scope.",
            "evidence://app-1",
            FEBRUARY,
            MARCH,
        )
        scoped = list_obligation_worklist(session, compliance, as_of=JANUARY)
        assert len(scoped) == 2
        assert {item.scope_reference for item in scoped} == {"tenant-1", "app-1"}
        assert obligation_next_action("unexpected") == obligation_next_action("unknown")


def test_obligation_version_number_conflict_is_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent append-only version collision is returned as a conflict, not a 500."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        _source_row, revision = _source(session, decision)
        obligation = _obligation(session, decision, revision)

        real_flush = session.flush
        flush_calls = 0

        def fail_flush(*_args: Any, **_kwargs: Any) -> None:
            """Simulate the unique-version race at the database boundary."""
            nonlocal flush_calls
            flush_calls += 1
            if flush_calls <= 2:
                real_flush(*_args, **_kwargs)
                return
            raise IntegrityError("insert", {}, RuntimeError("duplicate version"))

        monkeypatch.setattr(session, "flush", fail_flush)
        with pytest.raises(HTTPException, match="legal interpretation version"):
            add_legal_interpretation(session, decision, obligation.compliance_obligation_id, "Interpretation", "authority://1")


def test_unique_source_race_is_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A database uniqueness race is translated into the documented conflict."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        real_flush = session.flush
        flush_calls = 0

        def fail_flush(*_args: Any, **_kwargs: Any) -> None:
            """Simulate a concurrent unique source insert."""
            nonlocal flush_calls
            flush_calls += 1
            if flush_calls <= 2:
                real_flush(*_args, **_kwargs)
                return
            raise IntegrityError("insert", {}, RuntimeError("duplicate source"))

        monkeypatch.setattr(session, "flush", fail_flush)
        with pytest.raises(HTTPException, match="source code already exists"):
            create_regulatory_source(
                session,
                decision,
                "RACE-SOURCE",
                "regulation",
                "Concurrent source",
                "Authority",
                "https://example.test/race",
                "identifier_only",
            )


def test_obligation_rejects_wrong_purpose_bad_periods_and_cross_tenant_targets() -> None:
    """Purpose, period, tenant, and controlled-state boundaries fail closed."""
    factory = _factory()
    compliance = _decision()
    with factory() as session:
        with pytest.raises(HTTPException, match="compliance_governance"):
            create_regulatory_source(session, _decision(PurposeCode.COVERAGE_REVIEW), "X", "regulation", "X", "A", "u", "unknown")
        source, revision = _source(session, compliance)
        with pytest.raises(HTTPException, match="already exists"):
            create_regulatory_source(session, compliance, source.source_code, "regulation", "X", "A", "u", "unknown")
        with pytest.raises(HTTPException, match="positive"):
            create_source_revision(session, compliance, source.regulatory_source_id, 0, JANUARY, FEBRUARY, "d", "x")
        with pytest.raises(HTTPException, match="already exists"):
            create_source_revision(session, compliance, source.regulatory_source_id, 1, JANUARY, FEBRUARY, "d", "x")
        with pytest.raises(HTTPException, match="reversed"):
            create_source_revision(session, compliance, source.regulatory_source_id, 2, JANUARY, FEBRUARY, "d", "x", withdrawn_at=JANUARY)
        obligation = _obligation(session, compliance, revision)
        with pytest.raises(HTTPException, match="jurisdiction code"):
            create_jurisdiction(session, compliance, "EU", "Duplicate EU", "regional")
        with pytest.raises(HTTPException, match="obligation code"):
            create_compliance_obligation(session, compliance, revision.source_revision_id, "DORA-ICT-01", "Duplicate", "Duplicate", "regulatory", "organization", "tenant-1", FEBRUARY)
        rule = create_applicability_rule(session, compliance, obligation.compliance_obligation_id, "Rule", "always review")
        second_obligation = create_compliance_obligation(session, compliance, revision.source_revision_id, "DORA-ICT-02", "Second", "Second", "regulatory", "organization", "tenant-1", FEBRUARY)
        with pytest.raises(HTTPException, match="rule and obligation"):
            decide_applicability(session, compliance, second_obligation.compliance_obligation_id, "pending_review", "organization", "tenant-1", "r", "e", FEBRUARY, MARCH, applicability_rule_id=rule.applicability_rule_id)
        first_decision = decide_applicability(session, compliance, obligation.compliance_obligation_id, "pending_review", "organization", "tenant-1", "r", "e", FEBRUARY, MARCH)
        with pytest.raises(HTTPException, match="superseded decision"):
            decide_applicability(session, compliance, second_obligation.compliance_obligation_id, "pending_review", "organization", "tenant-1", "r", "e", FEBRUARY, MARCH, supersedes_decision_id=first_decision.applicability_decision_id)
        with pytest.raises(HTTPException, match="supported applicability"):
            decide_applicability(session, compliance, obligation.compliance_obligation_id, "bad", "x", "y", "r", "e", FEBRUARY, MARCH)
        with pytest.raises(HTTPException, match="Name the commitment"):
            register_compliance_commitment(session, compliance, obligation.compliance_obligation_id, "", "Title", "contract", "counterparty", FEBRUARY)
        commitment = register_compliance_commitment(session, compliance, obligation.compliance_obligation_id, "C-1", "Commitment", "voluntary", "counterparty", FEBRUARY)
        with pytest.raises(HTTPException, match="commitment code"):
            register_compliance_commitment(session, compliance, obligation.compliance_obligation_id, commitment.commitment_code, "Duplicate", "voluntary", "counterparty", FEBRUARY)
        with pytest.raises(HTTPException, match="policy or internal"):
            link_obligation_requirement(session, compliance, obligation.compliance_obligation_id, "R", "R", "R")
        with pytest.raises(HTTPException, match="official control"):
            link_obligation_requirement(session, compliance, obligation.compliance_obligation_id, "R-CATALOG", "Catalog", "Catalog", policy_version_id="missing-policy", control_item_id="missing-control")
        policy_document = PolicyDocument(policy_document_id="draft-policy", tenant_id=compliance.tenant_id, policy_title="Draft", created_by_actor="officer", created_at=JANUARY, current_version_number=1)
        session.add(policy_document)
        session.flush()
        draft_version = PolicyVersion(policy_version_id="draft-version", tenant_id=compliance.tenant_id, policy_document_id=policy_document.policy_document_id, version_number=1, policy_body="Draft", authored_by_actor="officer", authored_at=JANUARY, is_finalized=False)
        session.add(draft_version)
        session.flush()
        with pytest.raises(HTTPException, match="finalized policy"):
            link_obligation_requirement(session, compliance, obligation.compliance_obligation_id, "R-DRAFT", "Draft", "Draft", policy_version_id=draft_version.policy_version_id)
        control_decision = _decision(PurposeCode.COVERAGE_REVIEW)
        first_control = create_control_foundation(session, control_decision, objective_code="OBJ-BOUNDARY", objective_title="Boundary", objective_statement="Boundary", control_code="IC-BOUNDARY-1", control_name="First", control_statement="First", control_type="preventive", execution_mode="manual", frequency="monthly", expected_evidence="Register", scope_type="organization", scope_reference="tenant-1", owner_reference="owner", effective_from=FEBRUARY)
        second_control = create_control_foundation(session, control_decision, objective_code="OBJ-BOUNDARY", objective_title="Boundary", objective_statement="Boundary", control_code="IC-BOUNDARY-2", control_name="Second", control_statement="Second", control_type="preventive", execution_mode="manual", frequency="monthly", expected_evidence="Register", scope_type="organization", scope_reference="tenant-2", owner_reference="owner", effective_from=FEBRUARY)
        with pytest.raises(HTTPException, match="internal control definition"):
            link_obligation_requirement(session, compliance, obligation.compliance_obligation_id, "R-MISSING-CONTROL", "Missing control", "The implementation needs its definition.", control_implementation_id=first_control.implementation.control_implementation_id)
        with pytest.raises(HTTPException, match="do not match"):
            link_obligation_requirement(session, compliance, obligation.compliance_obligation_id, "R-MISMATCH", "Mismatch", "Mismatch", internal_control_definition_id=first_control.definition.internal_control_definition_id, control_implementation_id=second_control.implementation.control_implementation_id)
        with pytest.raises(HTTPException, match="between 0 and 3660"):
            list_obligation_worklist(session, compliance, upcoming_days=-1)
        with pytest.raises(HTTPException, match="between 0 and 3660"):
            list_obligation_worklist(session, compliance, upcoming_days=3661)
        other = _decision(tenant_id="tenant-two")
        with pytest.raises(HTTPException, match="not on file"):
            create_compliance_obligation(session, other, revision.source_revision_id, "OTHER", "Other", "Other", "regulatory", "tenant", "two", FEBRUARY)
        with pytest.raises(HTTPException, match="not on file"):
            decide_applicability(session, compliance, "missing", "unknown", "organization", "tenant-1", "r", "e", FEBRUARY, MARCH)
        change = record_regulatory_change(session, compliance, revision.source_revision_id, "CHANGE-1", "Changed", "diff://1")
        with pytest.raises(HTTPException, match="change code"):
            record_regulatory_change(session, compliance, revision.source_revision_id, "CHANGE-1", "Duplicate", "diff://2")
        with pytest.raises(HTTPException, match="past"):
            assess_change_impact(session, compliance, change.regulatory_change_id, obligation.compliance_obligation_id, "pending", "Pending", "owner", "Plan", "required", due_at=JANUARY)


def test_obligation_history_is_database_immutable() -> None:
    """Source editions, decisions, and impact assessments cannot be rewritten or deleted."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        _source_row, revision = _source(session, decision)
        obligation = _obligation(session, decision, revision)
        applicability = decide_applicability(
            session,
            decision,
            obligation.compliance_obligation_id,
            "pending_review",
            "organization",
            "tenant-1",
            "Review is pending.",
            "evidence://review",
            FEBRUARY,
            MARCH,
        )
        change = record_regulatory_change(session, decision, revision.source_revision_id, "CHANGE-IMMUTABLE", "Changed", "diff://1")
        assessment = assess_change_impact(
            session,
            decision,
            change.regulatory_change_id,
            obligation.compliance_obligation_id,
            "no_change",
            "No policy change is needed.",
            "owner",
            "Monitor the next review.",
            "not_required",
        )
        session.commit()
        for model, identifier, values in (
            (SourceRevision, revision.source_revision_id, {"revision_summary": "tampered"}),
            (ApplicabilityDecision, applicability.applicability_decision_id, {"rationale": "tampered"}),
            (ChangeImpactAssessment, assessment.change_impact_assessment_id, {"impact_rationale": "tampered"}),
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(update(model).where(model.__table__.primary_key.columns.values()[0] == identifier).values(**values))
            session.rollback()
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(delete(model).where(model.__table__.primary_key.columns.values()[0] == identifier))
            session.rollback()


def test_obligation_http_workflow_uses_local_boundary() -> None:
    """The JSON workflow reaches source, obligation, decision, change, and impact endpoints."""
    client = TestClient(create_app(database_url="sqlite://", evidence_key=None))
    headers = {"X-Actor-Id": "officer", "X-Purpose": PurposeCode.COMPLIANCE_GOVERNANCE.value}
    source = client.post(
        "/obligations/sources",
        headers=headers,
        json={
            "source_code": "HTTP-LAW",
            "source_kind": "regulation",
            "source_title": "HTTP source",
            "issuing_authority": "Authority",
            "official_reference_url": "https://example.test/http",
            "license_classification": "identifier_only",
        },
    )
    assert source.status_code == 201
    source_id = source.json()["regulatory_source_id"]
    missing_timestamp = client.post(
        f"/obligations/sources/{source_id}/revisions",
        headers=headers,
        json={"revision_number": 2},
    )
    assert missing_timestamp.status_code == 400
    revision = client.post(
        f"/obligations/sources/{source_id}/revisions",
        headers=headers,
        json={
            "revision_number": 1,
            "publication_date": "2026-01-01T00:00:00",
            "effective_from": "2026-02-01T00:00:00",
            "content_digest": "sha256:http",
            "revision_summary": "HTTP revision",
        },
    )
    assert revision.status_code == 201
    obligation = client.post(
        "/obligations",
        headers=headers,
        json={
            "source_revision_id": revision.json()["source_revision_id"],
            "obligation_code": "HTTP-OB-1",
            "obligation_title": "HTTP obligation",
            "obligation_description": "A realistic obligation.",
            "obligation_type": "regulatory",
            "scope_type": "organization",
            "scope_reference": "tenant-1",
            "effective_from": "2026-02-01T00:00:00",
        },
    )
    assert obligation.status_code == 201
    obligation_id = obligation.json()["compliance_obligation_id"]
    decision = client.post(
        f"/obligations/{obligation_id}/applicability-decisions",
        headers=headers,
        json={
            "decision_code": "applicable",
            "scope_type": "organization",
            "scope_reference": "tenant-1",
            "rationale": "The tenant is in scope.",
            "evidence_reference": "evidence://http",
            "effective_from": "2026-02-01T00:00:00",
            "next_review_at": "2026-03-01T00:00:00",
        },
    )
    assert decision.status_code == 201
    policy = client.post(
        "/policy-documents",
        headers={"X-Actor-Id": "policy-officer", "X-Purpose": PurposeCode.POLICY_AUTHORING.value},
        json={
            "policy_title": "HTTP policy",
            "policy_body": "Review the obligation.",
            "control_refs": [],
        },
    )
    assert policy.status_code == 201
    requirement = client.post(
        f"/obligations/{obligation_id}/requirements",
        headers=headers,
        json={
            "requirement_code": "HTTP-REQ-1",
            "requirement_title": "HTTP policy link",
            "mapping_rationale": "The approved policy addresses the obligation.",
            "policy_version_id": policy.json()["current_version"]["policy_version_id"],
        },
    )
    assert requirement.status_code == 201
    assert requirement.json()["review_status"] == "proposed"
    change = client.post(
        "/obligations/changes",
        headers=headers,
        json={
            "source_revision_id": revision.json()["source_revision_id"],
            "change_code": "HTTP-CHANGE-1",
            "change_summary": "A changed source.",
            "source_diff_reference": "diff://http",
        },
    )
    assert change.status_code == 201
    assert change.json()["change_status"] == "detected"
    impact = client.post(
        f"/obligations/changes/{change.json()['regulatory_change_id']}/impact-assessments",
        headers=headers,
        json={
            "compliance_obligation_id": obligation_id,
            "impact_status": "pending",
            "impact_rationale": "Needs triage.",
            "assigned_owner_reference": "owner",
            "implementation_plan": "Review source and policy.",
            "reapproval_status": "required",
        },
    )
    assert impact.status_code == 201
    listing = client.get("/obligations", headers={"X-Purpose": PurposeCode.COMPLIANCE_GOVERNANCE.value})
    assert listing.status_code == 200
    assert listing.json()["obligations"][0]["applicability_code"] == "applicable"


def test_obligation_read_uses_verified_keyverse_tenant() -> None:
    """Protected obligation reads take tenant identity from the signed bearer token."""
    client, private_key = _protected_client()
    response = client.get(
        "/obligations",
        headers={
            "Authorization": f"Bearer {_protected_token(private_key)}",
            "X-Purpose": PurposeCode.COMPLIANCE_GOVERNANCE.value,
        },
    )
    assert response.status_code == 200
    assert response.json()["obligations"] == []


def test_obligation_write_routes_require_write_scope_and_bind_identity() -> None:
    """Protected obligation writes require their scope and preserve verified identity."""
    client, private_key = _protected_client()
    read_headers = {
        "Authorization": f"Bearer {_protected_token(private_key)}",
        "X-Purpose": PurposeCode.COMPLIANCE_GOVERNANCE.value,
    }
    write_headers = {
        "Authorization": f"Bearer {_protected_token(private_key, 'grc.compliance.write')}",
        "X-Purpose": PurposeCode.COMPLIANCE_GOVERNANCE.value,
    }
    for path in (
        "/obligations/sources",
        "/obligations/sources/missing/revisions",
        "/obligations",
        "/obligations/missing/applicability-decisions",
        "/obligations/missing/requirements",
        "/obligations/changes",
        "/obligations/changes/missing/impact-assessments",
    ):
        assert client.post(path, headers=read_headers, json={}).status_code == 403
    source = client.post(
        "/obligations/sources",
        headers=write_headers,
        json={
            "source_code": "KEYVERSE-SOURCE",
            "source_kind": "regulation",
            "source_title": "Protected source",
            "issuing_authority": "Authority",
            "official_reference_url": "https://example.test/protected",
            "license_classification": "identifier_only",
        },
    )
    assert source.status_code == 201
    with client.app.state.session_factory() as session:
        stored = session.query(RegulatorySource).filter_by(source_code="KEYVERSE-SOURCE").one()
        assert stored.tenant_id == "tenant-1"
        assert stored.created_by_actor == "keyverse-compliance-officer"
