"""Real tenant-scoped workflows for the internal-control coverage model."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import ArgumentError, IntegrityError
from sqlalchemy.orm import sessionmaker

from cwl_grc.authorization import AuthorizationDecision, PurposeCode, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, get_control_item, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import build_engine, create_session_factory
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence
from cwl_grc.app import serialize_control
from cwl_grc.internal_controls import (
    ControlCoverageStatus,
    ControlRelation,
    ControlTestResultCode,
    approve_control_requirement_mapping,
    control_coverage_status,
    create_control_foundation,
    create_control_test_plan,
    list_control_coverage,
    next_action_for_coverage,
    record_control_exception,
    record_control_test_execution,
    record_control_test_result,
    record_evidence_usage,
)
from cwl_grc.migrations import apply_schema_migrations
from cwl_grc.models import (
    Base,
    ControlEvidenceBinding,
    ControlDefinitionVersion,
    ControlTestExecution,
    EvidenceRecord,
    EvidenceUsage,
)
from cwl_grc.policy import ControlRef, author_policy, list_policy_gaps


_JANUARY_START = datetime(2026, 1, 1)
_JANUARY_END = datetime(2026, 1, 31)


def _factory():  # noqa: ANN202
    """Return a guarded SQLite store with the official catalog and purposes."""
    factory = create_session_factory("sqlite://")
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()
    return factory


def _decision(
    purpose: PurposeCode = PurposeCode.COVERAGE_REVIEW,
    tenant_id: str = "local_development",
) -> AuthorizationDecision:
    """Return one deterministic officer decision for a test tenant."""
    return AuthorizationDecision("officer-reviewer", purpose, tenant_id)


def _foundation(session, decision, control_code: str = "IC-ACCESS-1"):  # noqa: ANN001, ANN202
    """Create one realistic published access-control foundation."""
    return create_control_foundation(
        session,
        decision,
        objective_code="OBJ-ACCESS",
        objective_title="Logical access governance",
        objective_statement="Access is granted, reviewed, and revoked through an approved process.",
        control_code=control_code,
        control_name="Logical access review",
        control_statement="Review access grants and removals against approved requests.",
        control_type="preventive",
        execution_mode="manual",
        frequency="monthly",
        expected_evidence="Approved access review register",
        scope_type="application",
        scope_reference="identity-service",
        owner_reference="access-owner",
        effective_from=_JANUARY_START,
    )


def _map(session, decision, foundation, identifier: str = "10.2.1"):  # noqa: ANN001
    """Approve a real CSAP mapping for a foundation."""
    return approve_control_requirement_mapping(
        session,
        decision,
        foundation.definition.internal_control_definition_id,
        FrameworkCode.CSAP_2026,
        identifier,
        ControlRelation.EQUIVALENT_TO.value,
        "The internal control covers the official access requirement.",
        valid_from=_JANUARY_START,
    )


def _plan(session, decision, foundation, effectiveness_type: str, due=None):  # noqa: ANN001
    """Create one test plan for the selected effectiveness dimension."""
    return create_control_test_plan(
        session,
        decision,
        foundation.definition_version.control_definition_version_id,
        foundation.implementation.control_implementation_id,
        f"{effectiveness_type.title()} access review",
        effectiveness_type,
        "Inspect the approved register and reconcile a sample.",
        "January access requests",
        "monthly",
        next_test_due_at=due,
    )


def _execution(session, decision, plan, start=_JANUARY_START, end=_JANUARY_END):  # noqa: ANN001
    """Record a completed historical execution for a plan."""
    return record_control_test_execution(
        session,
        decision,
        plan.test_plan_id,
        start,
        end,
        "Five sampled access requests",
        "The sample was reconciled to approved requests.",
    )


def _evidence(session, evidence_id: str, collected_at: datetime) -> EvidenceRecord:  # noqa: ANN001
    """Insert one encrypted evidence record with an exact collection date."""
    record = EvidenceRecord(
        evidence_record_id=evidence_id,
        tenant_id="local_development",
        evidence_title="January access review register",
        collector_actor="officer-reviewer",
        purpose_code=PurposeCode.EVIDENCE_BINDING.value,
        ciphertext_payload=EvidenceCipher(None, allow_ephemeral=True).encrypt("Exact register"),
        collected_at=collected_at,
    )
    session.add(record)
    session.flush()
    return record


def test_internal_control_full_lifecycle_separates_design_and_operating_effectiveness() -> None:
    """A real workflow reaches operating effectiveness only after a scoped test result."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.1")
        assert control is not None
        assert control_coverage_status(session, control.control_item_id, decision.tenant_id) is ControlCoverageStatus.UNKNOWN
        assert control in list_control_items(session, FrameworkCode.CSAP_2026)

        foundation = _foundation(session, decision)
        _map(session, decision, foundation)
        assert control_coverage_status(session, control.control_item_id, decision.tenant_id) is ControlCoverageStatus.IMPLEMENTED_NOT_TESTED

        design_plan = _plan(session, decision, foundation, "design")
        design_execution = _execution(session, decision, design_plan)
        record_control_test_result(
            session,
            decision,
            design_execution.test_execution_id,
            ControlTestResultCode.EFFECTIVE.value,
            "The control design has an accountable owner and an approval step.",
        )
        assert control_coverage_status(session, control.control_item_id, decision.tenant_id) is ControlCoverageStatus.DESIGN_EFFECTIVE

        operating_plan = _plan(
            session,
            decision,
            foundation,
            "operating",
            due=datetime(2026, 12, 31),
        )
        operating_execution = _execution(session, decision, operating_plan)
        evidence = _evidence(session, "evidence-january", datetime(2026, 1, 15))
        usage = record_evidence_usage(
            session,
            _decision(PurposeCode.EVIDENCE_BINDING),
            evidence.evidence_record_id,
            operating_execution.test_execution_id,
            "supporting",
            "The register supports the January operating sample.",
        )
        assert usage.usage_status == "supporting"
        result = record_control_test_result(
            session,
            decision,
            operating_execution.test_execution_id,
            ControlTestResultCode.EFFECTIVE.value,
            "All sampled access changes matched approved requests.",
        )
        assert result.result_code == "effective"
        assert control_coverage_status(
            session,
            control.control_item_id,
            decision.tenant_id,
            now=datetime(2026, 2, 1),
        ) is ControlCoverageStatus.OPERATING_EFFECTIVE

        coverage = list_control_coverage(
            session,
            FrameworkCode.CSAP_2026,
            tenant_id=decision.tenant_id,
            now=datetime(2026, 2, 1),
        )
        projected = next(item for item in coverage if item.control_item.control_item_id == control.control_item_id)
        assert projected.status is ControlCoverageStatus.OPERATING_EFFECTIVE
        assert control not in list_uncovered_controls(session, FrameworkCode.CSAP_2026)
        assert serialize_control(control, covered=False)["covered"] is False
        assert serialize_control(control, coverage_status="unknown")["coverage_status"] == "unknown"


def test_internal_control_status_projection_covers_failure_exception_stale_and_not_applicable() -> None:
    """The projection preserves ineffective, exception, stale, and N/A distinctions."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        failed = _foundation(session, decision, "IC-FAILED-1")
        _map(session, decision, failed, "10.3.1")
        failed_plan = _plan(session, decision, failed, "operating")
        failed_execution = _execution(session, decision, failed_plan)
        record_control_test_result(
            session,
            decision,
            failed_execution.test_execution_id,
            ControlTestResultCode.INEFFECTIVE.value,
            "The sampled account remained active after the approved removal date.",
            deficiency_severity="high",
        )
        failed_control = get_control_item(session, FrameworkCode.CSAP_2026, "10.3.1")
        assert failed_control is not None
        assert control_coverage_status(session, failed_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.INEFFECTIVE
        deficiency_count = session.execute(text("SELECT COUNT(*) FROM control_deficiency")).scalar_one()
        assert deficiency_count == 1

        exception = record_control_exception(
            session,
            decision,
            failed.implementation.control_implementation_id,
            "Emergency account removal was delayed while the service was unavailable.",
            _JANUARY_START,
            datetime(2027, 1, 31),
        )
        assert exception.exception_status == "approved"
        assert control_coverage_status(
            session,
            failed_control.control_item_id,
            decision.tenant_id,
            now=datetime(2026, 1, 15),
        ) is ControlCoverageStatus.EXCEPTION
        exception.exception_status = "expired"
        session.flush()
        assert control_coverage_status(
            session,
            failed_control.control_item_id,
            decision.tenant_id,
            now=datetime(2027, 2, 1),
        ) is ControlCoverageStatus.INEFFECTIVE
        open_exception = record_control_exception(
            session,
            decision,
            failed.implementation.control_implementation_id,
            "Pending review does not authorize masking the failed result.",
            _JANUARY_START,
            exception_status="open",
        )
        assert open_exception.approved_by is None
        assert control_coverage_status(session, failed_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.INEFFECTIVE

        stale = _foundation(session, decision, "IC-STALE-1")
        _map(session, decision, stale, "10.2.2")
        stale_plan = _plan(session, decision, stale, "operating", due=datetime(2025, 12, 31))
        stale_execution = _execution(session, decision, stale_plan)
        record_control_test_result(
            session,
            decision,
            stale_execution.test_execution_id,
            ControlTestResultCode.EFFECTIVE.value,
            "The historical sample passed.",
        )
        stale_control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.2")
        assert stale_control is not None
        assert control_coverage_status(session, stale_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.STALE

        not_applicable = _foundation(session, decision, "IC-NA-1")
        _map(session, decision, not_applicable, "12.3.1")
        na_plan = _plan(session, decision, not_applicable, "design")
        na_execution = _execution(session, decision, na_plan)
        record_control_test_result(
            session,
            decision,
            na_execution.test_execution_id,
            ControlTestResultCode.NOT_APPLICABLE.value,
            "The scoped service does not process cryptographic keys.",
        )
        na_control = get_control_item(session, FrameworkCode.CSAP_2026, "12.3.1")
        assert na_control is not None
        assert control_coverage_status(session, na_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.NOT_APPLICABLE
        policy = author_policy(
            session,
            _decision(PurposeCode.POLICY_AUTHORING),
            "Cryptography applicability policy",
            "This scoped service does not process cryptographic keys.",
            [ControlRef(FrameworkCode.CSAP_2026, "12.3.1")],
        )
        assert list_policy_gaps(session, policy.policy_document_id, tenant_id=decision.tenant_id) == []

        not_applicable.implementation.implementation_status = "retired"
        session.flush()
        assert control_coverage_status(session, na_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.UNKNOWN
        planned = _foundation(session, decision, "IC-PLANNED-1")
        _map(session, decision, planned, "1.1.1")
        planned.implementation.implementation_status = "planned"
        session.flush()
        planned_control = get_control_item(session, FrameworkCode.CSAP_2026, "1.1.1")
        assert planned_control is not None
        assert control_coverage_status(session, planned_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.UNKNOWN

        not_tested = _foundation(session, decision, "IC-NOT-TESTED-1")
        _map(session, decision, not_tested, "10.1.1")
        not_tested_plan = _plan(session, decision, not_tested, "design")
        not_tested_execution = _execution(session, decision, not_tested_plan)
        record_control_test_result(
            session,
            decision,
            not_tested_execution.test_execution_id,
            ControlTestResultCode.NOT_TESTED.value,
            "The assigned reviewer did not complete the test.",
        )
        not_tested_control = get_control_item(session, FrameworkCode.CSAP_2026, "10.1.1")
        assert not_tested_control is not None
        assert control_coverage_status(session, not_tested_control.control_item_id, decision.tenant_id) is ControlCoverageStatus.IMPLEMENTED_NOT_TESTED

    for status in ControlCoverageStatus:
        assert next_action_for_coverage(status)
    assert next_action_for_coverage("not-a-status") == next_action_for_coverage(ControlCoverageStatus.UNKNOWN)


def test_latest_operating_effective_result_does_not_inherit_old_staleness() -> None:
    """A fresh operating pass must not be downgraded by an older overdue pass."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        foundation = _foundation(session, decision, "IC-LATEST-OPERATING-1")
        _map(session, decision, foundation, "10.2.1")
        old_plan = _plan(session, decision, foundation, "operating", due=datetime(2025, 12, 31))
        with patch("cwl_grc.internal_controls.datetime") as old_clock:
            old_clock.now.return_value = datetime(2026, 1, 15)
            record_control_test_result(
                session,
                decision,
                _execution(session, decision, old_plan).test_execution_id,
                ControlTestResultCode.EFFECTIVE.value,
                "The older sample passed.",
            )
        recent_plan = _plan(session, decision, foundation, "operating", due=datetime(2026, 3, 31))
        with patch("cwl_grc.internal_controls.datetime") as recent_clock:
            recent_clock.now.return_value = datetime(2026, 2, 15)
            record_control_test_result(
                session,
                decision,
                _execution(session, decision, recent_plan).test_execution_id,
                ControlTestResultCode.EFFECTIVE.value,
                "The current sample passed.",
            )
        session.flush()
        control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.1")
        assert control is not None
        assert control_coverage_status(
            session,
            control.control_item_id,
            decision.tenant_id,
            datetime(2026, 2, 20),
        ) is ControlCoverageStatus.OPERATING_EFFECTIVE


def test_latest_operating_retest_clears_historical_ineffective_result() -> None:
    """A passing retest must supersede an older ineffective result on the same plan."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        foundation = _foundation(session, decision, "IC-RETEST-OPERATING-1")
        _map(session, decision, foundation, "10.2.2")
        plan = _plan(session, decision, foundation, "operating", due=datetime(2026, 3, 31))
        old_execution = _execution(session, decision, plan)
        with patch("cwl_grc.internal_controls.datetime") as old_clock:
            old_clock.now.return_value = datetime(2026, 1, 15)
            record_control_test_result(
                session,
                decision,
                old_execution.test_execution_id,
                ControlTestResultCode.INEFFECTIVE.value,
                "The historical sample found an unresolved access review gap.",
            )
        recent_execution = _execution(
            session,
            decision,
            plan,
            start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 28),
        )
        with patch("cwl_grc.internal_controls.datetime") as recent_clock:
            recent_clock.now.return_value = datetime(2026, 2, 15)
            record_control_test_result(
                session,
                decision,
                recent_execution.test_execution_id,
                ControlTestResultCode.EFFECTIVE.value,
                "The current retest confirms the access review gap is remediated.",
            )
        session.flush()
        control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.2")
        assert control is not None
        assert control_coverage_status(
            session,
            control.control_item_id,
            decision.tenant_id,
            datetime(2026, 2, 20),
        ) is ControlCoverageStatus.OPERATING_EFFECTIVE


def test_internal_control_rejections_are_tenant_and_purpose_bound() -> None:
    """Invalid workflows fail closed without allowing guessed tenant identifiers."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        with pytest.raises(HTTPException, match="coverage_review"):
            _foundation(session, _decision(PurposeCode.EVIDENCE_BINDING))
        with pytest.raises(ValueError, match="control type"):
            create_control_foundation(
                session,
                decision,
                objective_code="OBJ-BAD",
                objective_title="Objective",
                objective_statement="Statement",
                control_code="IC-BAD",
                control_name="Bad control",
                control_statement="Statement",
                control_type="unknown",
                execution_mode="manual",
                frequency="monthly",
                expected_evidence="register",
                scope_type="application",
                scope_reference="app",
                owner_reference="owner",
            )
        foundation = _foundation(session, decision)
        open_exception = record_control_exception(
            session,
            decision,
            foundation.implementation.control_implementation_id,
            "Temporary review window.",
            _JANUARY_START,
            exception_status="open",
        )
        assert open_exception.approved_by is None
        with pytest.raises(ValueError, match="exception status"):
            record_control_exception(
                session,
                decision,
                foundation.implementation.control_implementation_id,
                "Bad exception state",
                _JANUARY_START,
                exception_status="invalid",
            )
        with pytest.raises(ValueError, match="exception reason"):
            record_control_exception(
                session,
                decision,
                foundation.implementation.control_implementation_id,
                " ",
                _JANUARY_START,
            )
        with pytest.raises(ValueError, match="period end"):
            record_control_exception(
                session,
                decision,
                foundation.implementation.control_implementation_id,
                "Reversed exception",
                _JANUARY_END,
                _JANUARY_START,
            )
        with pytest.raises(HTTPException, match="not on file"):
            approve_control_requirement_mapping(
                session,
                _decision(PurposeCode.COVERAGE_REVIEW, "tenant-b"),
                foundation.definition.internal_control_definition_id,
                FrameworkCode.CSAP_2026,
                "10.2.1",
                ControlRelation.EQUIVALENT_TO.value,
                "cross-tenant mapping",
            )
        with pytest.raises(HTTPException, match="different statement"):
            create_control_foundation(
                session,
                decision,
                objective_code="OBJ-ACCESS",
                objective_title="Changed objective",
                objective_statement="Changed statement",
                control_code="IC-OTHER",
                control_name="Other control",
                control_statement="Statement",
                control_type="preventive",
                execution_mode="manual",
                frequency="monthly",
                expected_evidence="register",
                scope_type="application",
                scope_reference="app",
                owner_reference="owner",
            )
        with pytest.raises(HTTPException, match="already exists"):
            _foundation(session, decision)
        with pytest.raises(ValueError, match="mapping relation"):
            approve_control_requirement_mapping(
                session,
                decision,
                foundation.definition.internal_control_definition_id,
                FrameworkCode.CSAP_2026,
                "10.2.1",
                "overlaps",
                "invalid relation",
            )
        with pytest.raises(HTTPException, match="not in the catalog"):
            approve_control_requirement_mapping(
                session,
                decision,
                foundation.definition.internal_control_definition_id,
                FrameworkCode.CSAP_2026,
                "99.9.9",
                ControlRelation.EQUIVALENT_TO.value,
                "missing official identifier",
            )
        _map(session, decision, foundation)
        with pytest.raises(HTTPException, match="already exists"):
            _map(session, decision, foundation)
        with pytest.raises(ValueError, match="period end"):
            approve_control_requirement_mapping(
                session,
                decision,
                foundation.definition.internal_control_definition_id,
                FrameworkCode.CSAP_2026,
                "10.2.2",
                ControlRelation.SUBSET_OF.value,
                "reversed period",
                valid_from=_JANUARY_END,
                valid_to=_JANUARY_START,
            )
        other = _foundation(session, decision, "IC-OTHER-1")
        with pytest.raises(HTTPException, match="do not match"):
            create_control_test_plan(
                session,
                decision,
                foundation.definition_version.control_definition_version_id,
                other.implementation.control_implementation_id,
                "Mismatched plan",
                "design",
                "inspect",
                "sample",
                "monthly",
            )
        with pytest.raises(HTTPException, match="not on file"):
            create_control_test_plan(
                session,
                decision,
                "missing-version",
                foundation.implementation.control_implementation_id,
                "Missing plan",
                "design",
                "inspect",
                "sample",
                "monthly",
            )
        with pytest.raises(ValueError, match="effectiveness type"):
            create_control_test_plan(
                session,
                decision,
                foundation.definition_version.control_definition_version_id,
                foundation.implementation.control_implementation_id,
                "Bad plan",
                "other",
                "inspect",
                "sample",
                "monthly",
            )
        plan = _plan(session, decision, foundation, "operating")
        with pytest.raises(HTTPException, match="not on file"):
            record_control_test_execution(
                session,
                decision,
                "missing-plan",
                _JANUARY_START,
                _JANUARY_END,
                "sample",
                "rationale",
            )
        with pytest.raises(ValueError, match="period end"):
            record_control_test_execution(
                session,
                decision,
                plan.test_plan_id,
                _JANUARY_END,
                _JANUARY_START,
                "sample",
                "rationale",
            )
        execution = _execution(session, decision, plan)
        with pytest.raises(HTTPException, match="not on file"):
            record_control_test_result(session, decision, "missing-execution", "effective", "missing")
        with pytest.raises(ValueError, match="test result"):
            record_control_test_result(session, decision, execution.test_execution_id, "bad", "bad")
        with pytest.raises(ValueError, match="result rationale"):
            record_control_test_result(session, decision, execution.test_execution_id, "effective", " ")
        record_control_test_result(session, decision, execution.test_execution_id, "effective", "passed")
        with pytest.raises(HTTPException, match="already has"):
            record_control_test_result(session, decision, execution.test_execution_id, "effective", "again")

        evidence = _evidence(session, "evidence-outside", datetime(2026, 2, 1))
        with pytest.raises(HTTPException, match="requires evidence_binding"):
            record_evidence_usage(
                session,
                decision,
                evidence.evidence_record_id,
                execution.test_execution_id,
                "supporting",
                "wrong purpose",
            )
        with pytest.raises(HTTPException, match="not on file"):
            record_evidence_usage(
                session,
                _decision(PurposeCode.EVIDENCE_BINDING),
                "missing-evidence",
                execution.test_execution_id,
                "supporting",
                "missing evidence",
            )
        with pytest.raises(HTTPException, match="outside"):
            record_evidence_usage(
                session,
                _decision(PurposeCode.EVIDENCE_BINDING),
                evidence.evidence_record_id,
                execution.test_execution_id,
                "supporting",
                "outside period",
            )
        inside_complete = _evidence(session, "evidence-inside-complete", datetime(2026, 1, 15))
        with pytest.raises(ValueError, match="evidence usage status"):
            record_evidence_usage(
                session,
                _decision(PurposeCode.EVIDENCE_BINDING),
                inside_complete.evidence_record_id,
                execution.test_execution_id,
                "unknown",
                "invalid status",
            )
        with pytest.raises(ValueError, match="usage note"):
            record_evidence_usage(
                session,
                _decision(PurposeCode.EVIDENCE_BINDING),
                inside_complete.evidence_record_id,
                execution.test_execution_id,
                "supporting",
                " ",
            )
        incomplete_execution = ControlTestExecution(
            test_execution_id=uuid4().hex,
            tenant_id=decision.tenant_id,
            test_plan_id=plan.test_plan_id,
            control_implementation_id=foundation.implementation.control_implementation_id,
            test_period_start=_JANUARY_START,
            test_period_end=_JANUARY_END,
            executed_at=_JANUARY_START,
            performed_by=decision.actor_identifier,
            sample_description="In-progress sample",
            execution_status="in_progress",
            rationale="The test is not complete.",
            created_at=_JANUARY_START,
        )
        session.add(incomplete_execution)
        session.flush()
        inside = _evidence(session, "evidence-inside", datetime(2026, 1, 15))
        with pytest.raises(HTTPException, match="completed"):
            record_evidence_usage(
                session,
                _decision(PurposeCode.EVIDENCE_BINDING),
                inside.evidence_record_id,
                incomplete_execution.test_execution_id,
                "supporting",
                "incomplete test",
            )

        tenant_b = _decision(PurposeCode.COVERAGE_REVIEW, "tenant-b")
        with pytest.raises(HTTPException, match="not on file"):
            create_control_test_plan(
                session,
                tenant_b,
                foundation.definition_version.control_definition_version_id,
                foundation.implementation.control_implementation_id,
                "Cross-tenant plan",
                "design",
                "inspect",
                "sample",
                "monthly",
            )


def test_legacy_binding_backfill_and_sqlite_immutability() -> None:
    """Legacy direct bindings become unassessed and finalized histories cannot mutate."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.1")
        assert control is not None
        evidence = _evidence(session, "legacy-evidence", _JANUARY_START)
        binding = bind_control_evidence(
            session,
            _decision(PurposeCode.EVIDENCE_BINDING),
            FrameworkCode.CSAP_2026,
            "10.2.1",
            evidence.evidence_record_id,
        )
        session.commit()
        assert control_coverage_status(session, control.control_item_id, decision.tenant_id) is ControlCoverageStatus.UNASSESSED
        usage_count = session.execute(
            text("SELECT COUNT(*) FROM evidence_usage WHERE legacy_binding_id = :binding_id"),
            {"binding_id": binding.binding_id},
        ).scalar_one()
        assert usage_count == 0

        foundation = _foundation(session, decision)
        _map(session, decision, foundation)
        plan = _plan(session, decision, foundation, "operating")
        execution = _execution(session, decision, plan)
        modern_evidence = _evidence(session, "modern-evidence", datetime(2026, 1, 15))
        record_evidence_usage(
            session,
            _decision(PurposeCode.EVIDENCE_BINDING),
            modern_evidence.evidence_record_id,
            execution.test_execution_id,
            "supporting",
            "Supports the test.",
        )
        record_control_test_result(session, decision, execution.test_execution_id, "effective", "Passed.")
        session.commit()

    with factory() as session:
        for table, identifier_column, identifier in (
            ("control_definition_version", "control_definition_version_id", foundation.definition_version.control_definition_version_id),
            ("control_test_execution", "test_execution_id", execution.test_execution_id),
            ("control_test_result", "test_result_id", session.execute(text("SELECT test_result_id FROM control_test_result LIMIT 1")).scalar_one()),
            ("evidence_usage", "evidence_usage_id", session.execute(text("SELECT evidence_usage_id FROM evidence_usage WHERE legacy_binding_id IS NULL LIMIT 1")).scalar_one()),
        ):
            with pytest.raises(IntegrityError):
                session.execute(
                    text(f"UPDATE {table} SET {identifier_column} = :replacement WHERE {identifier_column} = :identifier"),
                    {"replacement": uuid4().hex, "identifier": identifier},
                )
                session.commit()
            session.rollback()


def test_sqlite_composite_foreign_keys_reject_cross_tenant_internal_rows() -> None:
    """SQLite parity rejects a child row that guesses another tenant's parent."""
    factory = _factory()
    decision = _decision()
    with factory() as session:
        foundation = _foundation(session, decision)
        session.commit()
        session.add(
            ControlDefinitionVersion(
                control_definition_version_id=uuid4().hex,
                tenant_id="tenant-b",
                internal_control_definition_id=foundation.definition.internal_control_definition_id,
                version_number=2,
                control_statement="Cross-tenant statement",
                control_type="preventive",
                execution_mode="manual",
                frequency="monthly",
                expected_evidence="register",
                effective_from=_JANUARY_START,
                published_at=_JANUARY_START,
                created_by_actor="tenant-b-officer",
                created_at=_JANUARY_START,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_factory_rejects_unknown_dialect_after_generic_engine_path() -> None:
    """The non-SQLite/PostgreSQL engine path still delegates to SQLAlchemy."""
    with pytest.raises(ArgumentError):
        build_engine("unknown-grc-dialect://")


def test_migration_backfills_preexisting_direct_binding_as_unassessed() -> None:
    """The model migration preserves a preexisting direct binding without inventing effectiveness."""
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        evidence = _evidence(session, "migration-evidence", _JANUARY_START)
        long_evidence = _evidence(session, "migration-evidence-long", _JANUARY_START)
        control = get_control_item(session, FrameworkCode.CSAP_2026, "10.2.1")
        assert control is not None
        session.add(
            ControlEvidenceBinding(
                binding_id="migration-binding",
                tenant_id="local_development",
                control_item_id=control.control_item_id,
                evidence_record_id=evidence.evidence_record_id,
                bound_by_actor="legacy-officer",
                purpose_code=PurposeCode.EVIDENCE_BINDING.value,
                bound_at=_JANUARY_START,
            )
        )
        session.add(
            EvidenceUsage(
                evidence_usage_id="legacy-existing",
                tenant_id="local_development",
                evidence_record_id=evidence.evidence_record_id,
                legacy_binding_id="migration-binding",
                purpose_code=PurposeCode.EVIDENCE_BINDING.value,
                usage_status="unassessed",
                usage_note="Already backfilled.",
                used_by_actor="legacy-officer",
                used_at=_JANUARY_START,
            )
        )
        session.add(
            ControlEvidenceBinding(
                binding_id="b" * 64,
                tenant_id="local_development",
                control_item_id=control.control_item_id,
                evidence_record_id=long_evidence.evidence_record_id,
                bound_by_actor="legacy-officer",
                purpose_code=PurposeCode.EVIDENCE_BINDING.value,
                bound_at=_JANUARY_START,
            )
        )
        session.commit()

    apply_schema_migrations(engine)
    apply_schema_migrations(engine)
    with session_factory() as session:
        usage = session.execute(
            text(
                "SELECT usage_status, legacy_binding_id, control_implementation_id "
                "FROM evidence_usage WHERE legacy_binding_id = 'migration-binding'"
            )
        ).one()
        assert usage == ("unassessed", "migration-binding", None)
        long_usage_id = session.execute(
            text("SELECT evidence_usage_id FROM evidence_usage WHERE legacy_binding_id = :binding_id"),
            {"binding_id": "b" * 64},
        ).scalar_one()
        assert len(long_usage_id) == 64
