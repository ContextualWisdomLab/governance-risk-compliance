"""Tenant-scoped risk methodology, register, and immutable assessment workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.models import (
    ControlImplementation,
    ControlTestExecution,
    ControlTestPlan,
    ControlTestResult,
    EvidenceUsage,
    RiskAssessment,
    RiskAssessmentControlLink,
    RiskAcceptance,
    RiskClosure,
    RiskMethodology,
    RiskRegister,
    RiskTreatmentPlan,
)


_RISK_STATUSES = {"identified", "assessed", "treating", "accepted", "closed"}
_AGGREGATION_RULE = "minimum_operating_effective_factor_no_double_count"
_ROUNDING_POLICY = "nearest_integer_half_up"
_CONTROL_EFFECTIVENESS_METHOD = "completed_operating_test_with_supporting_evidence"


def next_action_for_risk(
    risk: RiskRegister,
    assessment: RiskAssessment | None,
    *,
    treatment: RiskTreatmentPlan | None = None,
    acceptance: RiskAcceptance | None = None,
    current: datetime | None = None,
) -> str:
    """Return the next officer action without implying that risk is certified away."""
    now = _normalize_utc(current or datetime.now(timezone.utc))
    if assessment is not None and risk.risk_status == "closed":
        return "Retain the immutable assessment and closure decision for audit review."
    if risk.next_review_at < now:
        return "Review this overdue risk and create a fresh assessment or approved follow-up."
    if assessment is None:
        return "Record an inherent and residual assessment using a versioned methodology."
    if (
        acceptance is not None
        and acceptance.risk_assessment_id == assessment.risk_assessment_id
        and acceptance.acceptance_status == "active"
        and acceptance.valid_from <= now < acceptance.valid_to
    ):
        return "Monitor the approved acceptance and complete the next review before it expires."
    if treatment is not None and treatment.plan_status in {"proposed", "approved", "in_progress"}:
        return "Advance the versioned treatment plan and retain completion evidence."
    if assessment.appetite_status == "above_appetite":
        return "Create a versioned treatment plan or a time-bounded approved acceptance."
    return "Monitor the next review date and preserve the assessment evidence references."


def create_risk_methodology(
    session: Session,
    decision: AuthorizationDecision,
    methodology_code: str,
    methodology_version: int,
    methodology_title: str,
    likelihood_scale_max: int,
    impact_scale_max: int,
    effective_control_factor_percent: int,
    appetite_threshold: int,
    tolerance_threshold: int,
) -> RiskMethodology:
    """Create one immutable, versioned risk calculation rule set."""
    _require_governance_purpose(decision)
    code = _required_text(methodology_code, "methodology code")
    title = _required_text(methodology_title, "methodology title")
    version = _positive_int(methodology_version, "methodology version")
    likelihood_max = _scale(likelihood_scale_max, "likelihood scale maximum")
    impact_max = _scale(impact_scale_max, "impact scale maximum")
    factor = _bounded_int(effective_control_factor_percent, "effective control factor", 0, 100)
    appetite = _bounded_int(appetite_threshold, "appetite threshold", 0, None)
    tolerance = _bounded_int(tolerance_threshold, "tolerance threshold", appetite, None)
    if (
        session.query(RiskMethodology)
        .filter_by(
            tenant_id=decision.tenant_id,
            methodology_code=code,
            methodology_version=version,
        )
        .one_or_none()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That risk methodology version already exists.")
    methodology = RiskMethodology(
        methodology_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        methodology_code=code,
        methodology_version=version,
        methodology_title=title,
        likelihood_scale_max=likelihood_max,
        impact_scale_max=impact_max,
        effective_control_factor_percent=factor,
        control_effectiveness_method=_CONTROL_EFFECTIVENESS_METHOD,
        appetite_threshold=appetite,
        tolerance_threshold=tolerance,
        aggregation_rule=_AGGREGATION_RULE,
        rounding_policy=_ROUNDING_POLICY,
        created_by_actor=decision.actor_identifier,
        created_at=_utc_now(),
    )
    session.add(methodology)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_risk_methodology",
        resource_kind="risk_methodology",
        resource_identifier=methodology.methodology_id,
    )
    return methodology


def create_risk_register(
    session: Session,
    decision: AuthorizationDecision,
    risk_code: str,
    risk_title: str,
    risk_scenario: str,
    risk_category: str,
    source_reference: str,
    affected_scope_type: str,
    affected_scope_reference: str,
    owner_reference: str,
    review_cadence_days: int,
) -> RiskRegister:
    """Create one stable tenant risk identity with an explicit review obligation."""
    _require_governance_purpose(decision)
    fields = (
        (risk_code, "risk code"),
        (risk_title, "risk title"),
        (risk_scenario, "risk scenario"),
        (risk_category, "risk category"),
        (source_reference, "source reference"),
        (affected_scope_type, "affected scope type"),
        (affected_scope_reference, "affected scope reference"),
        (owner_reference, "owner reference"),
    )
    values = [_required_text(value, label) for value, label in fields]
    cadence = _positive_int(review_cadence_days, "review cadence")
    if (
        session.query(RiskRegister)
        .filter_by(tenant_id=decision.tenant_id, risk_code=values[0])
        .one_or_none()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That risk code already exists for this tenant.")
    now = _utc_now()
    risk = RiskRegister(
        risk_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        risk_code=values[0],
        risk_title=values[1],
        risk_scenario=values[2],
        risk_category=values[3],
        source_reference=values[4],
        affected_scope_type=values[5],
        affected_scope_reference=values[6],
        owner_reference=values[7],
        risk_status="identified",
        review_cadence_days=cadence,
        revision_number=1,
        next_review_at=now + timedelta(days=cadence),
        created_by_actor=decision.actor_identifier,
        created_at=now,
    )
    session.add(risk)
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_risk_register",
        resource_kind="risk_register",
        resource_identifier=risk.risk_id,
    )
    return risk


def assess_risk(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    methodology_id: str,
    likelihood: int,
    impact: int,
    assessment_rationale: str,
    next_review_at: datetime,
    control_links: object,
    *,
    expected_revision_number: int,
    decision_reference: str | None = None,
) -> RiskAssessment:
    """Append one immutable assessment backed only by same-tenant tested controls and evidence usage."""
    _require_governance_purpose(decision)
    risk = (
        session.query(RiskRegister)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id)
        .with_for_update()
        .one_or_none()
    )
    if risk is None:
        raise HTTPException(status_code=404, detail="That risk is not on file.")
    methodology = (
        session.query(RiskMethodology)
        .filter_by(tenant_id=decision.tenant_id, methodology_id=methodology_id)
        .one_or_none()
    )
    if methodology is None:
        raise HTTPException(status_code=404, detail="That risk methodology is not on file.")
    expected = _positive_int(expected_revision_number, "expected risk revision")
    if risk.revision_number != expected:
        raise HTTPException(status_code=409, detail="The risk changed; reload before assessing it again.")
    likelihood_value = _bounded_int(likelihood, "likelihood", 1, methodology.likelihood_scale_max)
    impact_value = _bounded_int(impact, "impact", 1, methodology.impact_scale_max)
    rationale = _required_text(assessment_rationale, "assessment rationale")
    review_at = _normalize_utc(next_review_at)
    links = _validated_control_links(
        session,
        decision,
        control_links,
        methodology.effective_control_factor_percent,
    )
    inherent_score = likelihood_value * impact_value
    factor = min((item[0] for item in links), default=100)
    residual_score = int(
        (Decimal(inherent_score) * Decimal(factor) / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    appetite_status = (
        "within_appetite" if residual_score <= methodology.appetite_threshold else "above_appetite"
    )
    number = (
        session.query(func.max(RiskAssessment.assessment_number))
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk.risk_id)
        .scalar()
        or 0
    ) + 1
    now = _utc_now()
    assessment = RiskAssessment(
        risk_assessment_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        risk_id=risk.risk_id,
        methodology_id=methodology.methodology_id,
        assessment_number=number,
        likelihood=likelihood_value,
        impact=impact_value,
        inherent_score=inherent_score,
        control_effectiveness_factor_percent=factor,
        residual_score=residual_score,
        appetite_status=appetite_status,
        aggregation_rule=methodology.aggregation_rule,
        assessment_rationale=rationale,
        decision_reference=_optional_text(decision_reference, "decision reference"),
        assessed_by_actor=decision.actor_identifier,
        assessed_at=now,
        next_review_at=review_at,
    )
    session.add(assessment)
    session.flush()
    for link_factor, implementation, result, usage, plan in links:
        session.add(
            RiskAssessmentControlLink(
                risk_assessment_control_link_id=uuid4().hex,
                tenant_id=decision.tenant_id,
                risk_assessment_id=assessment.risk_assessment_id,
                control_implementation_id=implementation.control_implementation_id,
                control_test_result_id=result.test_result_id,
                evidence_usage_id=usage.evidence_usage_id,
                result_code=result.result_code,
                effectiveness_type=plan.effectiveness_type,
                linked_at=now,
            )
        )
    risk.revision_number += 1
    risk.risk_status = "assessed"
    risk.next_review_at = review_at
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="assess_risk",
        resource_kind="risk_assessment",
        resource_identifier=assessment.risk_assessment_id,
    )
    return assessment


def list_risk_register(session: Session, decision: AuthorizationDecision) -> list[RiskRegister]:
    """List only the exact tenant's risk identities in review order."""
    _require_governance_purpose(decision)
    return (
        session.query(RiskRegister)
        .filter_by(tenant_id=decision.tenant_id)
        .order_by(RiskRegister.next_review_at, RiskRegister.risk_id)
        .all()
    )


def latest_risk_assessment(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
) -> RiskAssessment | None:
    """Return the latest immutable assessment for one exact-tenant risk."""
    _require_governance_purpose(decision)
    return (
        session.query(RiskAssessment)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id)
        .order_by(RiskAssessment.assessment_number.desc())
        .first()
    )


def create_risk_treatment(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    treatment_strategy: str,
    plan_title: str,
    plan_description: str,
    owner_reference: str,
    due_at: datetime,
    *,
    expected_revision_number: int,
) -> RiskTreatmentPlan:
    """Create the next immutable treatment-plan version for an assessed risk."""
    _require_governance_purpose(decision)
    risk = _locked_risk(session, decision, risk_id, expected_revision_number)
    if latest_risk_assessment(session, decision, risk_id) is None:
        raise HTTPException(status_code=409, detail="Assess the risk before creating treatment.")
    strategy = _required_text(treatment_strategy, "treatment strategy")
    if strategy not in {"avoid", "reduce", "transfer", "accept"}:
        raise HTTPException(status_code=400, detail="Use a supported treatment strategy.")
    title = _required_text(plan_title, "treatment plan title")
    description = _required_text(plan_description, "treatment plan description")
    owner = _required_text(owner_reference, "treatment owner reference")
    due = _normalize_utc(due_at)
    if due <= _utc_now():
        raise HTTPException(status_code=400, detail="The treatment due date must be in the future.")
    version = (
        session.query(func.max(RiskTreatmentPlan.plan_version))
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk.risk_id)
        .scalar()
        or 0
    ) + 1
    plan = RiskTreatmentPlan(
        risk_treatment_plan_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        risk_id=risk.risk_id,
        plan_version=version,
        treatment_strategy=strategy,
        plan_title=title,
        plan_description=description,
        owner_reference=owner,
        due_at=due,
        plan_status="proposed",
        created_by_actor=decision.actor_identifier,
        created_at=_utc_now(),
    )
    session.add(plan)
    risk.revision_number += 1
    risk.risk_status = "treating"
    risk.next_review_at = due
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_risk_treatment",
        resource_kind="risk_treatment_plan",
        resource_identifier=plan.risk_treatment_plan_id,
    )
    return plan


def latest_risk_treatment(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
) -> RiskTreatmentPlan | None:
    """Return the latest immutable treatment-plan version for one risk."""
    _require_governance_purpose(decision)
    return (
        session.query(RiskTreatmentPlan)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id)
        .order_by(RiskTreatmentPlan.plan_version.desc())
        .first()
    )


def create_risk_acceptance(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    risk_assessment_id: str,
    acceptance_reference: str,
    acceptance_rationale: str,
    valid_from: datetime,
    valid_to: datetime,
    *,
    expected_revision_number: int,
    escalation_reference: str | None = None,
) -> RiskAcceptance:
    """Create an independent, time-bounded acceptance for the latest above-appetite assessment."""
    _require_governance_purpose(decision)
    risk = _locked_risk(session, decision, risk_id, expected_revision_number)
    assessment = (
        session.query(RiskAssessment)
        .filter_by(
            tenant_id=decision.tenant_id,
            risk_assessment_id=risk_assessment_id,
            risk_id=risk.risk_id,
        )
        .one_or_none()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="That risk assessment is not on file.")
    if latest_risk_assessment(session, decision, risk.risk_id).risk_assessment_id != assessment.risk_assessment_id:
        raise HTTPException(status_code=409, detail="Acceptance must reference the latest risk assessment.")
    if assessment.appetite_status != "above_appetite":
        raise HTTPException(status_code=409, detail="Only an above-appetite assessment can be accepted.")
    if assessment.assessed_by_actor == decision.actor_identifier:
        raise HTTPException(status_code=403, detail="Acceptance requires an independent approving actor.")
    methodology = (
        session.query(RiskMethodology)
        .filter_by(tenant_id=decision.tenant_id, methodology_id=assessment.methodology_id)
        .one_or_none()
    )
    if methodology is None:
        raise HTTPException(status_code=409, detail="The assessment methodology is not on file.")
    reference = _required_text(acceptance_reference, "acceptance reference")
    rationale = _required_text(acceptance_rationale, "acceptance rationale")
    start = _normalize_utc(valid_from)
    end = _normalize_utc(valid_to)
    now = _utc_now()
    if end <= start or end <= now or start > now:
        raise HTTPException(status_code=400, detail="Acceptance must have a current, future-ending period.")
    escalation = _optional_text(escalation_reference, "escalation reference")
    if assessment.residual_score > methodology.tolerance_threshold and escalation is None:
        raise HTTPException(status_code=400, detail="An above-tolerance risk requires escalation reference.")
    if (
        session.query(RiskAcceptance)
        .filter_by(
            tenant_id=decision.tenant_id,
            risk_id=risk.risk_id,
            risk_assessment_id=assessment.risk_assessment_id,
        )
        .one_or_none()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That risk assessment already has an acceptance.")
    acceptance = RiskAcceptance(
        risk_acceptance_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        risk_id=risk.risk_id,
        risk_assessment_id=assessment.risk_assessment_id,
        acceptance_reference=reference,
        acceptance_rationale=rationale,
        escalation_reference=escalation,
        accepted_by_actor=decision.actor_identifier,
        accepted_at=now,
        valid_from=start,
        valid_to=end,
        acceptance_status="active",
    )
    session.add(acceptance)
    risk.revision_number += 1
    risk.risk_status = "accepted"
    risk.next_review_at = end
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="create_risk_acceptance",
        resource_kind="risk_acceptance",
        resource_identifier=acceptance.risk_acceptance_id,
    )
    return acceptance


def latest_risk_acceptance(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    *,
    risk_assessment_id: str | None = None,
) -> RiskAcceptance | None:
    """Return the latest active acceptance for one risk or exact assessment."""
    _require_governance_purpose(decision)
    query = (
        session.query(RiskAcceptance)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id, acceptance_status="active")
    )
    if risk_assessment_id is not None:
        query = query.filter_by(risk_assessment_id=risk_assessment_id)
    return query.order_by(RiskAcceptance.valid_to.desc(), RiskAcceptance.accepted_at.desc()).first()


def create_risk_closure(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    risk_assessment_id: str,
    closure_reference: str,
    closure_rationale: str,
    closure_evidence_reference: str,
    *,
    expected_revision_number: int,
) -> RiskClosure:
    """Approve immutable closure only after a current within-appetite reassessment."""
    _require_governance_purpose(decision)
    risk = _locked_risk(session, decision, risk_id, expected_revision_number)
    assessment = (
        session.query(RiskAssessment)
        .filter_by(
            tenant_id=decision.tenant_id,
            risk_assessment_id=risk_assessment_id,
            risk_id=risk.risk_id,
        )
        .one_or_none()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="That risk assessment is not on file.")
    latest = latest_risk_assessment(session, decision, risk.risk_id)
    if latest is None or latest.risk_assessment_id != assessment.risk_assessment_id:
        raise HTTPException(status_code=409, detail="Closure must reference the latest risk assessment.")
    if assessment.appetite_status != "within_appetite":
        raise HTTPException(status_code=409, detail="Only a within-appetite assessment can be closed.")
    acceptance = latest_risk_acceptance(session, decision, risk.risk_id)
    now = _utc_now()
    if acceptance is not None and acceptance.valid_from <= now < acceptance.valid_to:
        raise HTTPException(status_code=409, detail="An active risk acceptance must expire before closure.")
    if assessment.assessed_by_actor == decision.actor_identifier:
        raise HTTPException(status_code=403, detail="Closure requires an independent approving actor.")
    reference = _required_text(closure_reference, "closure reference")
    rationale = _required_text(closure_rationale, "closure rationale")
    evidence_reference = _required_text(closure_evidence_reference, "closure evidence reference")
    if (
        session.query(RiskClosure)
        .filter_by(
            tenant_id=decision.tenant_id,
            risk_id=risk.risk_id,
            risk_assessment_id=assessment.risk_assessment_id,
        )
        .one_or_none()
        is not None
    ):
        raise HTTPException(status_code=409, detail="That risk assessment already has a closure.")
    closure = RiskClosure(
        risk_closure_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        risk_id=risk.risk_id,
        risk_assessment_id=assessment.risk_assessment_id,
        closure_reference=reference,
        closure_rationale=rationale,
        closure_evidence_reference=evidence_reference,
        closed_by_actor=decision.actor_identifier,
        closed_at=now,
    )
    session.add(closure)
    risk.revision_number += 1
    risk.risk_status = "closed"
    risk.next_review_at = now
    session.flush()
    record_audit_event(
        session,
        decision,
        action_name="close_risk",
        resource_kind="risk_closure",
        resource_identifier=closure.risk_closure_id,
    )
    return closure


def latest_risk_closure(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
) -> RiskClosure | None:
    """Return the latest immutable closure approval for one risk."""
    _require_governance_purpose(decision)
    return (
        session.query(RiskClosure)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id)
        .order_by(RiskClosure.closed_at.desc())
        .first()
    )


def _locked_risk(
    session: Session,
    decision: AuthorizationDecision,
    risk_id: str,
    expected_revision_number: int,
) -> RiskRegister:
    """Load and optimistically lock one tenant risk before a disposition write."""
    risk = (
        session.query(RiskRegister)
        .filter_by(tenant_id=decision.tenant_id, risk_id=risk_id)
        .with_for_update()
        .one_or_none()
    )
    if risk is None:
        raise HTTPException(status_code=404, detail="That risk is not on file.")
    expected = _positive_int(expected_revision_number, "expected risk revision")
    if risk.revision_number != expected:
        raise HTTPException(status_code=409, detail="The risk changed; reload before recording disposition.")
    return risk


def _validated_control_links(
    session: Session,
    decision: AuthorizationDecision,
    value: object,
    effective_factor_percent: int,
) -> list[tuple[int, ControlImplementation, ControlTestResult, EvidenceUsage, ControlTestPlan]]:
    """Validate explicit internal-control implementation, test-result, and evidence-use links."""
    if value is None:
        raise HTTPException(status_code=400, detail="Control links must be a list.")
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="Control links must be a list.")
    links = []
    seen_implementations: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each control link must be an object.")
        implementation_id = _required_text(item.get("control_implementation_id"), "control implementation")
        result_id = _required_text(item.get("control_test_result_id"), "control test result")
        usage_id = _required_text(item.get("evidence_usage_id"), "evidence usage")
        if implementation_id in seen_implementations:
            raise HTTPException(status_code=409, detail="A control implementation may be linked once per assessment.")
        seen_implementations.add(implementation_id)
        implementation = (
            session.query(ControlImplementation)
            .filter_by(tenant_id=decision.tenant_id, control_implementation_id=implementation_id)
            .one_or_none()
        )
        result = (
            session.query(ControlTestResult)
            .filter_by(tenant_id=decision.tenant_id, test_result_id=result_id)
            .one_or_none()
        )
        usage = (
            session.query(EvidenceUsage)
            .filter_by(tenant_id=decision.tenant_id, evidence_usage_id=usage_id)
            .one_or_none()
        )
        if implementation is None or result is None or usage is None:
            raise HTTPException(status_code=404, detail="A linked control or evidence record is not on file.")
        if implementation.implementation_status != "implemented":
            raise HTTPException(status_code=409, detail="Only implemented controls can mitigate a risk.")
        execution = (
            session.query(ControlTestExecution)
            .filter_by(tenant_id=decision.tenant_id, test_execution_id=result.test_execution_id)
            .one_or_none()
        )
        if execution is None or execution.control_implementation_id != implementation.control_implementation_id:
            raise HTTPException(status_code=409, detail="The test result is not for the linked implementation.")
        if usage.control_implementation_id != implementation.control_implementation_id:
            raise HTTPException(status_code=409, detail="The evidence usage is not for the linked implementation.")
        if usage.control_test_execution_id != execution.test_execution_id:
            raise HTTPException(status_code=409, detail="The evidence usage is not for the test result execution.")
        plan = (
            session.query(ControlTestPlan)
            .filter_by(tenant_id=decision.tenant_id, test_plan_id=execution.test_plan_id)
            .one_or_none()
        )
        if plan is None:
            raise HTTPException(status_code=409, detail="The test result plan is not on file.")
        factor = 100
        if (
            result.result_code == "effective"
            and plan.effectiveness_type == "operating"
            and usage.usage_status == "supporting"
            and execution.execution_status == "completed"
        ):
            factor = effective_factor_percent
        links.append((factor, implementation, result, usage, plan))
    return links


def _require_governance_purpose(decision: AuthorizationDecision) -> None:
    """Require the declared compliance-governance purpose for risk work."""
    if decision.purpose_code is not PurposeCode.COMPLIANCE_GOVERNANCE:
        raise HTTPException(status_code=403, detail="This action requires compliance_governance.")


def _required_text(value: object, field_name: str) -> str:
    """Return one trimmed, non-empty domain field."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"Name the {field_name}.")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    """Return one optional trimmed domain field."""
    if value is None or value == "":
        return None
    return _required_text(value, field_name)


def _positive_int(value: object, field_name: str) -> int:
    """Require a positive integer without accepting booleans as numbers."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HTTPException(status_code=400, detail=f"The {field_name} must be a positive integer.")
    return value


def _bounded_int(value: object, field_name: str, minimum: int, maximum: int | None) -> int:
    """Require an integer within one methodology-defined range."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HTTPException(status_code=400, detail=f"The {field_name} is outside its allowed scale.")
    if maximum is not None and value > maximum:
        raise HTTPException(status_code=400, detail=f"The {field_name} is outside its allowed scale.")
    return value


def _scale(value: object, field_name: str) -> int:
    """Require one bounded 2-10 likelihood or impact scale."""
    return _bounded_int(value, field_name, 2, 10)


def _normalize_utc(value: datetime) -> datetime:
    """Store aware timestamps as naive UTC values used by the existing schema."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_now() -> datetime:
    """Return the current UTC timestamp in the product's timestamp format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
