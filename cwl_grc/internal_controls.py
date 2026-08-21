"""Tenant-scoped internal-control definitions, testing, and coverage truth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.catalog import FrameworkCode, get_control_item
from cwl_grc.models import (
    ControlDeficiency,
    ControlDefinitionVersion,
    ControlEvidenceBinding,
    ControlException,
    ControlImplementation,
    ControlObjective,
    ControlOwnerAssignment,
    ControlRequirementMapping,
    ControlTestExecution,
    ControlTestPlan,
    ControlTestResult,
    ControlItem,
    EvidenceRecord,
    EvidenceUsage,
    InternalControlDefinition,
)


class ControlRelation(StrEnum):
    """Reviewed semantic relation between an internal and external control."""

    EQUIVALENT_TO = "equivalent_to"
    SUBSET_OF = "subset_of"
    SUPERSET_OF = "superset_of"
    INTERSECTS_WITH = "intersects_with"


class ControlTestResultCode(StrEnum):
    """Allowed design or operating effectiveness conclusions."""

    EFFECTIVE = "effective"
    INEFFECTIVE = "ineffective"
    NOT_TESTED = "not_tested"
    NOT_APPLICABLE = "not_applicable"


class ControlCoverageStatus(StrEnum):
    """Buyer-facing status that never equates an artifact with effectiveness."""

    UNKNOWN = "unknown"
    UNASSESSED = "unassessed"
    IMPLEMENTED_NOT_TESTED = "implemented_not_tested"
    DESIGN_EFFECTIVE = "design_effective"
    OPERATING_EFFECTIVE = "operating_effective"
    INEFFECTIVE = "ineffective"
    EXCEPTION = "exception"
    STALE = "stale"
    NOT_APPLICABLE = "not_applicable"


_COVERAGE_ACTIONS = {
    ControlCoverageStatus.UNKNOWN.value: "Define and review an internal control for this requirement.",
    ControlCoverageStatus.UNASSESSED.value: "Treat legacy evidence as unassessed and create a control test.",
    ControlCoverageStatus.IMPLEMENTED_NOT_TESTED.value: "Run the applicable design or operating control test.",
    ControlCoverageStatus.DESIGN_EFFECTIVE.value: "Complete the operating-effectiveness test before claiming coverage.",
    ControlCoverageStatus.OPERATING_EFFECTIVE.value: "Review the next scheduled test and preserve supporting evidence.",
    ControlCoverageStatus.INEFFECTIVE.value: "Remediate the deficiency and schedule an independent retest.",
    ControlCoverageStatus.EXCEPTION.value: "Review the time-bounded exception and its compensating action.",
    ControlCoverageStatus.STALE.value: "Run a fresh test because the previous conclusion is stale.",
    ControlCoverageStatus.NOT_APPLICABLE.value: "Retain the authorized applicability decision and its evidence.",
}


@dataclass(frozen=True)
class ControlFoundation:
    """The definition, published revision, implementation, and owner created together."""

    objective: ControlObjective
    definition: InternalControlDefinition
    definition_version: ControlDefinitionVersion
    implementation: ControlImplementation
    owner_assignment: ControlOwnerAssignment


@dataclass(frozen=True)
class ControlCoverage:
    """One external requirement and its reviewed internal-control status."""

    control_item: ControlItem
    status: ControlCoverageStatus


def next_action_for_coverage(status: ControlCoverageStatus | str) -> str:
    """Return the buyer's next action for one explicit coverage status."""
    return _COVERAGE_ACTIONS.get(str(status), _COVERAGE_ACTIONS[ControlCoverageStatus.UNKNOWN.value])


def create_control_foundation(
    session: Session,
    decision: AuthorizationDecision,
    *,
    objective_code: str,
    objective_title: str,
    objective_statement: str,
    control_code: str,
    control_name: str,
    control_statement: str,
    control_type: str,
    execution_mode: str,
    frequency: str,
    expected_evidence: str,
    scope_type: str,
    scope_reference: str,
    owner_reference: str,
    effective_from: datetime | None = None,
) -> ControlFoundation:
    """Create one published control definition with a scoped implementation and owner."""
    _require_control_purpose(decision)
    now = _normalize_utc(effective_from or datetime.now(timezone.utc))
    objective_code = _required_text(objective_code, "objective code")
    objective_title = _required_text(objective_title, "objective title")
    objective_statement = _required_text(objective_statement, "objective statement")
    control_code = _required_text(control_code, "control code")
    control_name = _required_text(control_name, "control name")
    control_statement = _required_text(control_statement, "control statement")
    frequency = _required_text(frequency, "test frequency")
    expected_evidence = _required_text(expected_evidence, "expected evidence")
    scope_reference = _required_text(scope_reference, "scope reference")
    owner_reference = _required_text(owner_reference, "owner reference")
    objective = (
        session.query(ControlObjective)
        .filter_by(tenant_id=decision.tenant_id, objective_code=objective_code)
        .one_or_none()
    )
    if objective is None:
        objective = ControlObjective(
            objective_id=uuid4().hex,
            tenant_id=decision.tenant_id,
            objective_code=objective_code,
            objective_title=objective_title,
            objective_statement=objective_statement,
            created_by_actor=decision.actor_identifier,
            created_at=now,
        )
        try:
            with session.begin_nested():
                session.add(objective)
                session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="That control objective already exists.",
            ) from exc
    elif (
        objective.objective_title != objective_title
        or objective.objective_statement != objective_statement
    ):
        raise HTTPException(
            status_code=409,
            detail="That control objective already exists with a different statement.",
        )
    if (
        session.query(InternalControlDefinition)
        .filter_by(tenant_id=decision.tenant_id, control_code=control_code)
        .first()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That internal control code already exists.")
    definition = InternalControlDefinition(
        internal_control_definition_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        objective_id=objective.objective_id,
        control_code=control_code,
        control_name=control_name,
        lifecycle_status="published",
        created_by_actor=decision.actor_identifier,
        created_at=now,
    )
    try:
        with session.begin_nested():
            session.add(definition)
            session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="That internal control code already exists.",
        ) from exc
    definition_version = ControlDefinitionVersion(
        control_definition_version_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        internal_control_definition_id=definition.internal_control_definition_id,
        version_number=1,
        control_statement=control_statement,
        control_type=_controlled_text(control_type, {"preventive", "detective", "corrective"}, "control type"),
        execution_mode=_controlled_text(execution_mode, {"manual", "automated", "hybrid"}, "execution mode"),
        frequency=frequency,
        expected_evidence=expected_evidence,
        effective_from=now,
        published_at=now,
        created_by_actor=decision.actor_identifier,
        created_at=now,
    )
    implementation = ControlImplementation(
        control_implementation_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        internal_control_definition_id=definition.internal_control_definition_id,
        scope_type=_controlled_text(
            scope_type,
            {"application", "process", "organization", "data_asset", "provider", "inherited_service"},
            "scope type",
        ),
        scope_reference=scope_reference,
        implementation_status="implemented",
        implemented_at=now,
        created_at=now,
    )
    owner_assignment = ControlOwnerAssignment(
        assignment_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        internal_control_definition_id=definition.internal_control_definition_id,
        control_implementation_id=implementation.control_implementation_id,
        owner_kind="accountable",
        owner_reference=owner_reference,
        valid_from=now,
        assigned_at=now,
    )
    session.add_all([definition_version, implementation, owner_assignment])
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_internal_control",
        resource_kind="internal_control_definition",
        resource_identifier=definition.internal_control_definition_id,
    )
    return ControlFoundation(objective, definition, definition_version, implementation, owner_assignment)


def approve_control_requirement_mapping(
    session: Session,
    decision: AuthorizationDecision,
    internal_control_definition_id: str,
    framework: FrameworkCode,
    catalog_identifier: str,
    relation_type: str,
    mapping_rationale: str,
    *,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> ControlRequirementMapping:
    """Approve one reviewed many-to-many mapping to an official catalog requirement."""
    _require_control_purpose(decision)
    relation = _controlled_text(
        relation_type,
        {item.value for item in ControlRelation},
        "mapping relation",
    )
    rationale = _required_text(mapping_rationale, "mapping rationale")
    definition = _get_definition(session, decision, internal_control_definition_id)
    control = get_control_item(session, framework, catalog_identifier)
    if control is None:
        raise HTTPException(status_code=404, detail="That official control is not in the catalog.")
    start = _normalize_utc(valid_from or datetime.now(timezone.utc))
    end = _normalize_utc(valid_to) if valid_to else None
    _valid_period(start, end)
    duplicate = (
        session.query(ControlRequirementMapping)
        .filter_by(
            tenant_id=decision.tenant_id,
            internal_control_definition_id=definition.internal_control_definition_id,
            control_item_id=control.control_item_id,
            relation_type=relation,
            valid_from=start,
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="That control mapping already exists.")
    mapping = ControlRequirementMapping(
        mapping_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        internal_control_definition_id=definition.internal_control_definition_id,
        control_item_id=control.control_item_id,
        relation_type=relation,
        review_status="approved",
        mapping_rationale=rationale,
        reviewed_by_actor=decision.actor_identifier,
        reviewed_at=start,
        valid_from=start,
        valid_to=end,
        created_at=start,
    )
    try:
        with session.begin_nested():
            session.add(mapping)
            session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="That control mapping already exists.") from exc
    record_audit_event(
        session,
        decision,
        action_name="approve_control_mapping",
        resource_kind="control_requirement_mapping",
        resource_identifier=mapping.mapping_id,
    )
    return mapping


def create_control_test_plan(
    session: Session,
    decision: AuthorizationDecision,
    control_definition_version_id: str,
    control_implementation_id: str,
    test_name: str,
    effectiveness_type: str,
    method: str,
    sample_population: str,
    test_frequency: str,
    *,
    next_test_due_at: datetime | None = None,
) -> ControlTestPlan:
    """Create a design or operating test plan tied to one version and implementation."""
    _require_control_purpose(decision)
    version = (
        session.query(ControlDefinitionVersion)
        .filter_by(
            tenant_id=decision.tenant_id,
            control_definition_version_id=control_definition_version_id,
        )
        .one_or_none()
    )
    implementation = _get_implementation(session, decision, control_implementation_id)
    if version is None:
        raise HTTPException(status_code=404, detail="That control definition version is not on file.")
    if version.internal_control_definition_id != implementation.internal_control_definition_id:
        raise HTTPException(status_code=409, detail="The test version and implementation do not match.")
    plan = ControlTestPlan(
        test_plan_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        control_definition_version_id=version.control_definition_version_id,
        control_implementation_id=implementation.control_implementation_id,
        test_name=_required_text(test_name, "test name"),
        effectiveness_type=_controlled_text(effectiveness_type, {"design", "operating"}, "effectiveness type"),
        method=_required_text(method, "test method"),
        sample_population=_required_text(sample_population, "sample population"),
        test_frequency=_required_text(test_frequency, "test frequency"),
        next_test_due_at=_normalize_utc(next_test_due_at) if next_test_due_at else None,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(plan)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_control_test_plan",
        resource_kind="control_test_plan",
        resource_identifier=plan.test_plan_id,
    )
    return plan


def record_control_test_execution(
    session: Session,
    decision: AuthorizationDecision,
    test_plan_id: str,
    test_period_start: datetime,
    test_period_end: datetime,
    sample_description: str,
    rationale: str,
) -> ControlTestExecution:
    """Record one completed historical test execution without rewriting its period."""
    _require_control_purpose(decision)
    plan = (
        session.query(ControlTestPlan)
        .filter_by(tenant_id=decision.tenant_id, test_plan_id=test_plan_id)
        .one_or_none()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="That control test plan is not on file.")
    start = _normalize_utc(test_period_start)
    end = _normalize_utc(test_period_end)
    _valid_period(start, end)
    execution = ControlTestExecution(
        test_execution_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        test_plan_id=plan.test_plan_id,
        control_implementation_id=plan.control_implementation_id,
        test_period_start=start,
        test_period_end=end,
        executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        performed_by=decision.actor_identifier,
        sample_description=_required_text(sample_description, "sample description"),
        execution_status="completed",
        rationale=_required_text(rationale, "test rationale"),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(execution)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="record_control_test_execution",
        resource_kind="control_test_execution",
        resource_identifier=execution.test_execution_id,
    )
    return execution


def record_control_test_result(
    session: Session,
    decision: AuthorizationDecision,
    test_execution_id: str,
    result_code: str,
    result_rationale: str,
    *,
    deficiency_severity: str = "medium",
    deficiency_due_at: datetime | None = None,
) -> ControlTestResult:
    """Record one immutable test conclusion and open a deficiency on failure."""
    _require_control_purpose(decision)
    execution = _get_test_execution(session, decision, test_execution_id)
    if (
        session.query(ControlTestResult)
        .filter_by(tenant_id=decision.tenant_id, test_execution_id=execution.test_execution_id)
        .first()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That test execution already has a result.")
    result = ControlTestResult(
        test_result_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        test_execution_id=execution.test_execution_id,
        result_code=_controlled_text(
            result_code,
            {item.value for item in ControlTestResultCode},
            "test result",
        ),
        result_rationale=_required_text(result_rationale, "result rationale"),
        determined_by=decision.actor_identifier,
        determined_at=datetime.now(timezone.utc).replace(tzinfo=None),
        reviewed_by=decision.actor_identifier,
        reviewed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    try:
        with session.begin_nested():
            session.add(result)
            if result.result_code == ControlTestResultCode.INEFFECTIVE.value:
                session.add(
                    ControlDeficiency(
                        deficiency_id=uuid4().hex,
                        tenant_id=decision.tenant_id,
                        control_implementation_id=execution.control_implementation_id,
                        test_execution_id=execution.test_execution_id,
                        deficiency_code=f"test_{execution.test_execution_id}",
                        severity=_controlled_text(
                            deficiency_severity,
                            {"low", "medium", "high", "critical"},
                            "deficiency severity",
                        ),
                        deficiency_description=result.result_rationale,
                        deficiency_status="open",
                        identified_at=result.determined_at,
                        due_at=_normalize_utc(deficiency_due_at) if deficiency_due_at else None,
                        created_at=result.created_at,
                    )
                )
            session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="That test execution already has a result.") from exc
    record_audit_event(
        session,
        decision,
        action_name="record_control_test_result",
        resource_kind="control_test_result",
        resource_identifier=result.test_result_id,
    )
    return result


def record_control_exception(
    session: Session,
    decision: AuthorizationDecision,
    control_implementation_id: str,
    exception_reason: str,
    valid_from: datetime,
    valid_to: datetime | None = None,
    *,
    exception_status: str = "approved",
) -> ControlException:
    """Record a reviewed, time-bounded exception for one implementation."""
    _require_control_purpose(decision)
    implementation = _get_implementation(session, decision, control_implementation_id)
    start = _normalize_utc(valid_from)
    end = _normalize_utc(valid_to) if valid_to else None
    _valid_period(start, end)
    status = _controlled_text(
        exception_status,
        {"open", "approved", "expired", "closed"},
        "exception status",
    )
    exception = ControlException(
        exception_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        control_implementation_id=implementation.control_implementation_id,
        exception_reason=_required_text(exception_reason, "exception reason"),
        exception_status=status,
        approved_by=decision.actor_identifier if status == "approved" else None,
        approved_at=start if status == "approved" else None,
        valid_from=start,
        valid_to=end,
        created_at=start,
    )
    session.add(exception)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="record_control_exception",
        resource_kind="control_exception",
        resource_identifier=exception.exception_id,
    )
    return exception


def record_evidence_usage(
    session: Session,
    decision: AuthorizationDecision,
    evidence_record_id: str,
    test_execution_id: str,
    usage_status: str,
    usage_note: str,
) -> EvidenceUsage:
    """Attach evidence to one completed test only when its collection period matches."""
    _require_evidence_purpose(decision)
    evidence = (
        session.query(EvidenceRecord)
        .filter_by(tenant_id=decision.tenant_id, evidence_record_id=evidence_record_id)
        .one_or_none()
    )
    execution = _get_test_execution(session, decision, test_execution_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="That evidence artifact is not on file.")
    if execution.execution_status != "completed":
        raise HTTPException(status_code=409, detail="Evidence usage requires a completed test.")
    if not execution.test_period_start <= evidence.collected_at <= execution.test_period_end:
        raise HTTPException(status_code=422, detail="Evidence collection is outside the test period.")
    status = _controlled_text(
        usage_status,
        {"supporting", "insufficient", "rejected"},
        "evidence usage status",
    )
    usage = EvidenceUsage(
        evidence_usage_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        evidence_record_id=evidence.evidence_record_id,
        control_implementation_id=execution.control_implementation_id,
        control_test_execution_id=execution.test_execution_id,
        purpose_code=decision.purpose_code.value,
        usage_status=status,
        usage_note=_required_text(usage_note, "evidence usage note"),
        used_by_actor=decision.actor_identifier,
        used_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(usage)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="record_evidence_usage",
        resource_kind="evidence_usage",
        resource_identifier=usage.evidence_usage_id,
    )
    return usage


def list_control_coverage(
    session: Session,
    framework: FrameworkCode | None,
    *,
    tenant_id: str,
    now: datetime | None = None,
) -> list[ControlCoverage]:
    """Return every external requirement with an explicit effectiveness status."""
    query = session.query(ControlItem)
    if framework is not None:
        query = query.filter(ControlItem.framework_key == framework.value)
    current = _normalize_utc(now or datetime.now(timezone.utc))
    return [
        ControlCoverage(item, control_coverage_status(session, item.control_item_id, tenant_id, current))
        for item in query.order_by(ControlItem.framework_key, ControlItem.catalog_identifier).all()
    ]


def control_coverage_status(
    session: Session,
    control_item_id: str,
    tenant_id: str,
    now: datetime | None = None,
) -> ControlCoverageStatus:
    """Derive one conservative status through approved mappings and test results."""
    current = _normalize_utc(now or datetime.now(timezone.utc))
    legacy = (
        session.query(ControlEvidenceBinding)
        .filter_by(tenant_id=tenant_id, control_item_id=control_item_id)
        .first()
        is not None
    )
    mappings = (
        session.query(ControlRequirementMapping)
        .filter(
            ControlRequirementMapping.tenant_id == tenant_id,
            ControlRequirementMapping.control_item_id == control_item_id,
            ControlRequirementMapping.review_status == "approved",
            ControlRequirementMapping.valid_from <= current,
            or_(
                ControlRequirementMapping.valid_to.is_(None),
                ControlRequirementMapping.valid_to >= current,
            ),
        )
        .all()
    )
    definition_ids = {mapping.internal_control_definition_id for mapping in mappings}
    if not definition_ids:
        return ControlCoverageStatus.UNASSESSED if legacy else ControlCoverageStatus.UNKNOWN
    implementations = (
        session.query(ControlImplementation)
        .join(
            InternalControlDefinition,
            InternalControlDefinition.internal_control_definition_id
            == ControlImplementation.internal_control_definition_id,
        )
        .filter(
            ControlImplementation.tenant_id == tenant_id,
            ControlImplementation.internal_control_definition_id.in_(definition_ids),
            ControlImplementation.implementation_status != "retired",
            InternalControlDefinition.lifecycle_status != "retired",
        )
        .all()
    )
    if not implementations:
        return ControlCoverageStatus.UNASSESSED if legacy else ControlCoverageStatus.UNKNOWN
    implementation_ids = {item.control_implementation_id for item in implementations}
    exception = (
        session.query(ControlException)
        .filter(
            ControlException.tenant_id == tenant_id,
            ControlException.control_implementation_id.in_(implementation_ids),
            ControlException.exception_status == "approved",
            ControlException.valid_from <= current,
            or_(ControlException.valid_to.is_(None), ControlException.valid_to >= current),
        )
        .first()
    )
    if exception is not None:
        return ControlCoverageStatus.EXCEPTION
    results = (
        session.query(ControlTestPlan, ControlTestResult)
        .join(
            ControlTestExecution,
            and_(
                ControlTestExecution.test_plan_id == ControlTestPlan.test_plan_id,
                ControlTestExecution.tenant_id == tenant_id,
            ),
        )
        .join(
            ControlTestResult,
            and_(
                ControlTestResult.test_execution_id == ControlTestExecution.test_execution_id,
                ControlTestResult.tenant_id == tenant_id,
            ),
        )
        .filter(
            ControlTestPlan.tenant_id == tenant_id,
            ControlTestPlan.control_implementation_id.in_(implementation_ids),
            ControlTestPlan.active.is_(True),
        )
        .order_by(
            ControlTestResult.determined_at.desc(),
            ControlTestResult.test_result_id.desc(),
        )
        .all()
    )
    latest_results_by_plan: dict[str, tuple[ControlTestPlan, ControlTestResult]] = {}
    for plan, result in results:
        latest_results_by_plan.setdefault(plan.test_plan_id, (plan, result))
    latest_results = tuple(latest_results_by_plan.values())
    if any(
        result.result_code == ControlTestResultCode.INEFFECTIVE.value
        for _, result in latest_results
    ):
        return ControlCoverageStatus.INEFFECTIVE
    saw_operating = False
    saw_design = False
    saw_not_applicable = False
    for plan, result in latest_results:
        if result.result_code == ControlTestResultCode.NOT_APPLICABLE.value:
            saw_not_applicable = True
        elif result.result_code == ControlTestResultCode.EFFECTIVE.value:
            if plan.effectiveness_type == "operating":
                if not saw_operating:
                    saw_operating = True
                    if plan.next_test_due_at is not None and plan.next_test_due_at < current:
                        return ControlCoverageStatus.STALE
            elif plan.effectiveness_type == "design":  # pragma: no branch - database check constraint
                saw_design = True
    if saw_operating:
        return ControlCoverageStatus.OPERATING_EFFECTIVE
    if saw_design:
        return ControlCoverageStatus.DESIGN_EFFECTIVE
    if saw_not_applicable:
        return ControlCoverageStatus.NOT_APPLICABLE
    if any(item.implementation_status == "implemented" for item in implementations):
        return ControlCoverageStatus.IMPLEMENTED_NOT_TESTED
    return ControlCoverageStatus.UNASSESSED if legacy else ControlCoverageStatus.UNKNOWN


def _get_definition(
    session: Session,
    decision: AuthorizationDecision,
    definition_id: str,
) -> InternalControlDefinition:
    """Load one tenant-owned internal control definition or hide its existence."""
    definition = (
        session.query(InternalControlDefinition)
        .filter_by(tenant_id=decision.tenant_id, internal_control_definition_id=definition_id)
        .one_or_none()
    )
    if definition is None:
        raise HTTPException(status_code=404, detail="That internal control is not on file.")
    return definition


def _get_implementation(
    session: Session,
    decision: AuthorizationDecision,
    implementation_id: str,
) -> ControlImplementation:
    """Load one tenant-owned implementation or hide its existence."""
    implementation = (
        session.query(ControlImplementation)
        .filter_by(tenant_id=decision.tenant_id, control_implementation_id=implementation_id)
        .one_or_none()
    )
    if implementation is None:
        raise HTTPException(status_code=404, detail="That control implementation is not on file.")
    return implementation


def _get_test_execution(
    session: Session,
    decision: AuthorizationDecision,
    execution_id: str,
) -> ControlTestExecution:
    """Load one tenant-owned test execution or hide its existence."""
    execution = (
        session.query(ControlTestExecution)
        .filter_by(tenant_id=decision.tenant_id, test_execution_id=execution_id)
        .one_or_none()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="That control test execution is not on file.")
    return execution


def _require_control_purpose(decision: AuthorizationDecision) -> None:
    """Require the coverage-review purpose for control model mutations."""
    if decision.purpose_code is not PurposeCode.COVERAGE_REVIEW:
        raise HTTPException(status_code=403, detail="This action requires coverage_review.")


def _require_evidence_purpose(decision: AuthorizationDecision) -> None:
    """Require the evidence-binding purpose for evidence usage mutations."""
    if decision.purpose_code is not PurposeCode.EVIDENCE_BINDING:
        raise HTTPException(status_code=403, detail="This action requires evidence_binding.")


def _required_text(value: str, label: str) -> str:
    """Return a non-empty trimmed text value for a domain field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text.")
    return value.strip()


def _controlled_text(value: str, allowed: set[str], label: str) -> str:
    """Return one member of a finite controlled vocabulary."""
    value = _required_text(value, label)
    if value not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}.")
    return value


def _normalize_utc(value: datetime) -> datetime:
    """Store aware timestamps as naive UTC values used by the existing schema."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _valid_period(start: datetime, end: datetime | None) -> None:
    """Reject a temporal interval whose end precedes its start."""
    if end is not None and end < start:
        raise ValueError("The period end cannot precede its start.")
