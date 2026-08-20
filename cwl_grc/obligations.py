"""Tenant-scoped obligation, applicability, and regulatory-change workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, TypeVar
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.models import (
    ApplicabilityDecision,
    ApplicabilityRule,
    ChangeImpactAssessment,
    ComplianceCommitment,
    ComplianceObligation,
    ControlImplementation,
    ControlItem,
    InternalControlDefinition,
    JurisdictionRecord,
    LegalInterpretation,
    ObligationOwnerAssignment,
    ObligationRequirement,
    PolicyVersion,
    RegulatoryChange,
    RegulatorySource,
    SourceRevision,
)


class ApplicabilityCode(StrEnum):
    """Controlled applicability decisions available to an officer."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    PARTIALLY_APPLICABLE = "partially_applicable"
    INHERITED = "inherited"
    COMPENSATING_CONTROL = "compensating_control"
    PENDING_REVIEW = "pending_review"
    UNKNOWN = "unknown"


class ImpactCode(StrEnum):
    """Controlled outcomes for a regulatory-change impact assessment."""

    PENDING = "pending"
    NO_CHANGE = "no_change"
    POLICY_UPDATE = "policy_update"
    CONTROL_UPDATE = "control_update"
    RETIRE_OBLIGATION = "retire_obligation"


class ReapprovalCode(StrEnum):
    """Controlled re-approval states after a source change."""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass(frozen=True)
class ObligationWorkItem:
    """One obligation projection with its latest applicability and next action."""

    obligation: ComplianceObligation
    applicability_code: str
    scope_type: str
    scope_reference: str
    next_review_at: datetime | None
    queue: str
    next_action: str


ModelT = TypeVar("ModelT")


def _require_compliance_purpose(decision: AuthorizationDecision) -> None:
    """Require the dedicated purpose before changing compliance truth."""
    if decision.purpose_code is not PurposeCode.COMPLIANCE_GOVERNANCE:
        raise HTTPException(
            status_code=403,
            detail="This action requires compliance_governance.",
        )


def _text(value: Any, label: str) -> str:
    """Require one non-empty text field at the trust boundary."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"Name the {label}.")
    return value.strip()


def _controlled(value: Any, allowed: set[str], label: str) -> str:
    """Accept only one declared state value."""
    normalized = _text(value, label)
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail=f"Use a supported {label}.")
    return normalized


def _utc(value: datetime | None = None) -> datetime:
    """Normalize an optional timestamp to naive UTC for existing database columns."""
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current
    return current.astimezone(timezone.utc).replace(tzinfo=None)


def _period(start: datetime, end: datetime | None, label: str = "effective period") -> None:
    """Reject reversed historical intervals."""
    if end is not None and end < start:
        raise HTTPException(status_code=400, detail=f"The {label} is reversed.")


def _same_tenant(session: Session, model: type[ModelT], identifier: str, tenant_id: str) -> ModelT:
    """Load one tenant-owned row or return a safe not-found response."""
    row = session.query(model).filter_by(**{model.__table__.primary_key.columns.keys()[0]: identifier, "tenant_id": tenant_id}).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="That compliance record is not on file.")
    return row


def create_jurisdiction(
    session: Session,
    decision: AuthorizationDecision,
    jurisdiction_code: str,
    jurisdiction_name: str,
    authority_level: str,
    official_reference: str | None = None,
) -> JurisdictionRecord:
    """Register a jurisdiction reference without copying an external domain body."""
    _require_compliance_purpose(decision)
    code = _text(jurisdiction_code, "jurisdiction code")
    if session.query(JurisdictionRecord).filter_by(tenant_id=decision.tenant_id, jurisdiction_code=code).first():
        raise HTTPException(status_code=409, detail="That jurisdiction code already exists.")
    jurisdiction = JurisdictionRecord(
        jurisdiction_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        jurisdiction_code=code,
        jurisdiction_name=_text(jurisdiction_name, "jurisdiction name"),
        authority_level=_text(authority_level, "authority level"),
        official_reference=official_reference.strip() if isinstance(official_reference, str) and official_reference.strip() else None,
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(jurisdiction)
    session.flush()
    record_audit_event(session, decision, "create_jurisdiction", "jurisdiction_record", jurisdiction.jurisdiction_id)
    return jurisdiction


def create_regulatory_source(
    session: Session,
    decision: AuthorizationDecision,
    source_code: str,
    source_kind: str,
    source_title: str,
    issuing_authority: str,
    official_reference_url: str,
    license_classification: str,
    *,
    source_artifact_reference: str | None = None,
) -> RegulatorySource:
    """Register an authoritative pointer and its lawful storage classification."""
    _require_compliance_purpose(decision)
    code = _text(source_code, "source code")
    if session.query(RegulatorySource).filter_by(tenant_id=decision.tenant_id, source_code=code).first():
        raise HTTPException(status_code=409, detail="That source code already exists.")
    source = RegulatorySource(
        regulatory_source_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        source_code=code,
        source_kind=_controlled(source_kind, {"legislation", "regulation", "contract", "voluntary", "internal_mandate"}, "source kind"),
        source_title=_text(source_title, "source title"),
        issuing_authority=_text(issuing_authority, "issuing authority"),
        official_reference_url=_text(official_reference_url, "official reference URL"),
        license_classification=_controlled(license_classification, {"identifier_only", "lawfully_stored", "restricted", "unknown"}, "license classification"),
        source_artifact_reference=source_artifact_reference.strip() if isinstance(source_artifact_reference, str) and source_artifact_reference.strip() else None,
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(source)
    session.flush()
    record_audit_event(session, decision, "create_regulatory_source", "regulatory_source", source.regulatory_source_id)
    return source


def create_source_revision(
    session: Session,
    decision: AuthorizationDecision,
    regulatory_source_id: str,
    revision_number: int,
    publication_date: datetime,
    effective_from: datetime,
    content_digest: str,
    revision_summary: str,
    *,
    withdrawn_at: datetime | None = None,
    immutable_artifact_reference: str | None = None,
) -> SourceRevision:
    """Append one immutable source edition with exact dates and a content digest."""
    _require_compliance_purpose(decision)
    source = _same_tenant(session, RegulatorySource, regulatory_source_id, decision.tenant_id)
    if isinstance(revision_number, bool) or not isinstance(revision_number, int) or revision_number <= 0:
        raise HTTPException(status_code=400, detail="Use a positive source revision number.")
    if session.query(SourceRevision).filter_by(tenant_id=decision.tenant_id, regulatory_source_id=source.regulatory_source_id, revision_number=revision_number).first():
        raise HTTPException(status_code=409, detail="That source revision already exists.")
    start = _utc(effective_from)
    withdrawn = _utc(withdrawn_at) if withdrawn_at else None
    _period(start, withdrawn, "source withdrawal period")
    revision = SourceRevision(
        source_revision_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        regulatory_source_id=source.regulatory_source_id,
        revision_number=revision_number,
        publication_date=_utc(publication_date),
        effective_from=start,
        withdrawn_at=withdrawn,
        content_digest=_text(content_digest, "source content digest"),
        immutable_artifact_reference=immutable_artifact_reference.strip() if isinstance(immutable_artifact_reference, str) and immutable_artifact_reference.strip() else None,
        revision_summary=_text(revision_summary, "revision summary"),
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(revision)
    session.flush()
    record_audit_event(session, decision, "create_source_revision", "source_revision", revision.source_revision_id)
    return revision


def create_compliance_obligation(
    session: Session,
    decision: AuthorizationDecision,
    source_revision_id: str,
    obligation_code: str,
    obligation_title: str,
    obligation_description: str,
    obligation_type: str,
    scope_type: str,
    scope_reference: str,
    effective_from: datetime,
    *,
    effective_to: datetime | None = None,
    jurisdiction_id: str | None = None,
) -> ComplianceObligation:
    """Create one immutable obligation linked to an exact source revision and scope."""
    _require_compliance_purpose(decision)
    revision = _same_tenant(session, SourceRevision, source_revision_id, decision.tenant_id)
    code = _text(obligation_code, "obligation code")
    if session.query(ComplianceObligation).filter_by(tenant_id=decision.tenant_id, obligation_code=code).first():
        raise HTTPException(status_code=409, detail="That obligation code already exists.")
    jurisdiction = None
    if jurisdiction_id:
        jurisdiction = _same_tenant(session, JurisdictionRecord, jurisdiction_id, decision.tenant_id)
    start = _utc(effective_from)
    end = _utc(effective_to) if effective_to else None
    _period(start, end)
    obligation = ComplianceObligation(
        compliance_obligation_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        source_revision_id=revision.source_revision_id,
        jurisdiction_id=jurisdiction.jurisdiction_id if jurisdiction else None,
        obligation_code=code,
        obligation_title=_text(obligation_title, "obligation title"),
        obligation_description=_text(obligation_description, "obligation description"),
        obligation_type=_controlled(obligation_type, {"statutory", "regulatory", "contractual", "voluntary", "internal_mandate"}, "obligation type"),
        scope_type=_text(scope_type, "obligation scope type"),
        scope_reference=_text(scope_reference, "obligation scope"),
        effective_from=start,
        effective_to=end,
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(obligation)
    session.flush()
    record_audit_event(session, decision, "create_compliance_obligation", "compliance_obligation", obligation.compliance_obligation_id)
    return obligation


def create_applicability_rule(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    rule_name: str,
    rule_expression: str,
) -> ApplicabilityRule:
    """Store a reviewable applicability rule proposal for one obligation."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    rule = ApplicabilityRule(
        applicability_rule_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        rule_name=_text(rule_name, "applicability rule name"),
        rule_expression=_text(rule_expression, "applicability rule expression"),
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(rule)
    session.flush()
    record_audit_event(session, decision, "create_applicability_rule", "applicability_rule", rule.applicability_rule_id)
    return rule


def decide_applicability(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    decision_code: str,
    scope_type: str,
    scope_reference: str,
    rationale: str,
    evidence_reference: str,
    effective_from: datetime,
    next_review_at: datetime,
    *,
    effective_to: datetime | None = None,
    applicability_rule_id: str | None = None,
    supersedes_decision_id: str | None = None,
) -> ApplicabilityDecision:
    """Append a rationale- and evidence-backed applicability decision."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    rule = None
    if applicability_rule_id:
        rule = _same_tenant(session, ApplicabilityRule, applicability_rule_id, decision.tenant_id)
        if rule.compliance_obligation_id != obligation.compliance_obligation_id:
            raise HTTPException(status_code=409, detail="The applicability rule and obligation do not match.")
    superseded = None
    if supersedes_decision_id:
        superseded = _same_tenant(session, ApplicabilityDecision, supersedes_decision_id, decision.tenant_id)
        if superseded.compliance_obligation_id != obligation.compliance_obligation_id:
            raise HTTPException(status_code=409, detail="The superseded decision and obligation do not match.")
    start = _utc(effective_from)
    end = _utc(effective_to) if effective_to else None
    _period(start, end)
    applicability = ApplicabilityDecision(
        applicability_decision_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        applicability_rule_id=rule.applicability_rule_id if rule else None,
        supersedes_decision_id=superseded.applicability_decision_id if superseded else None,
        decision_code=_controlled(decision_code, {item.value for item in ApplicabilityCode}, "applicability decision"),
        scope_type=_text(scope_type, "applicability scope type"),
        scope_reference=_text(scope_reference, "applicability scope"),
        rationale=_text(rationale, "applicability rationale"),
        evidence_reference=_text(evidence_reference, "applicability evidence reference"),
        decided_by_actor=decision.actor_identifier,
        decided_at=_utc(),
        effective_from=start,
        effective_to=end,
        next_review_at=_utc(next_review_at),
    )
    session.add(applicability)
    session.flush()
    record_audit_event(session, decision, "decide_applicability", "applicability_decision", applicability.applicability_decision_id)
    return applicability


def add_legal_interpretation(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    interpretation_text: str,
    authority_reference: str,
) -> LegalInterpretation:
    """Append an attributed interpretation reference while avoiding legal advice claims."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    number = (session.query(func.max(LegalInterpretation.interpretation_number)).filter_by(tenant_id=decision.tenant_id, compliance_obligation_id=obligation.compliance_obligation_id).scalar() or 0) + 1
    interpretation = LegalInterpretation(
        legal_interpretation_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        interpretation_number=number,
        interpretation_text=_text(interpretation_text, "legal interpretation"),
        authority_reference=_text(authority_reference, "interpretation authority"),
        interpreted_by_actor=decision.actor_identifier,
        interpreted_at=_utc(),
    )
    session.add(interpretation)
    session.flush()
    record_audit_event(session, decision, "add_legal_interpretation", "legal_interpretation", interpretation.legal_interpretation_id)
    return interpretation


def register_compliance_commitment(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    commitment_code: str,
    commitment_title: str,
    commitment_type: str,
    counterparty_reference: str,
    effective_from: datetime,
    *,
    effective_to: datetime | None = None,
) -> ComplianceCommitment:
    """Register a contract or voluntary commitment in the shared obligation workflow."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    code = _text(commitment_code, "commitment code")
    if session.query(ComplianceCommitment).filter_by(tenant_id=decision.tenant_id, commitment_code=code).first():
        raise HTTPException(status_code=409, detail="That commitment code already exists.")
    start = _utc(effective_from)
    end = _utc(effective_to) if effective_to else None
    _period(start, end, "commitment period")
    commitment = ComplianceCommitment(
        compliance_commitment_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        commitment_code=code,
        commitment_title=_text(commitment_title, "commitment title"),
        commitment_type=_controlled(commitment_type, {"contract", "voluntary"}, "commitment type"),
        counterparty_reference=_text(counterparty_reference, "commitment counterparty"),
        effective_from=start,
        effective_to=end,
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(commitment)
    session.flush()
    record_audit_event(session, decision, "register_compliance_commitment", "compliance_commitment", commitment.compliance_commitment_id)
    return commitment


def assign_obligation_owner(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    owner_kind: str,
    owner_reference: str,
    valid_from: datetime,
    *,
    valid_to: datetime | None = None,
) -> ObligationOwnerAssignment:
    """Append a temporal obligation owner reference owned by another domain."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    start = _utc(valid_from)
    end = _utc(valid_to) if valid_to else None
    _period(start, end, "owner period")
    assignment = ObligationOwnerAssignment(
        obligation_owner_assignment_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        owner_kind=_controlled(owner_kind, {"accountable", "legal", "operator", "reviewer"}, "owner kind"),
        owner_reference=_text(owner_reference, "owner reference"),
        valid_from=start,
        valid_to=end,
        assigned_by_actor=decision.actor_identifier,
        assigned_at=_utc(),
    )
    session.add(assignment)
    session.flush()
    record_audit_event(session, decision, "assign_obligation_owner", "obligation_owner_assignment", assignment.obligation_owner_assignment_id)
    return assignment


def link_obligation_requirement(
    session: Session,
    decision: AuthorizationDecision,
    compliance_obligation_id: str,
    requirement_code: str,
    requirement_title: str,
    mapping_rationale: str,
    *,
    policy_version_id: str | None = None,
    internal_control_definition_id: str | None = None,
    control_implementation_id: str | None = None,
    control_item_id: str | None = None,
    source_locator: str | None = None,
) -> ObligationRequirement:
    """Create a reviewed obligation link to a finalized policy or internal control."""
    _require_compliance_purpose(decision)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    if not policy_version_id and not internal_control_definition_id:
        raise HTTPException(status_code=400, detail="Link the obligation to a policy or internal control.")
    catalog_item = None
    if control_item_id:
        catalog_item = session.get(ControlItem, control_item_id)
        if catalog_item is None:
            raise HTTPException(status_code=404, detail="That official control is not in the catalog.")
    policy = None
    if policy_version_id:
        policy = _same_tenant(session, PolicyVersion, policy_version_id, decision.tenant_id)
        if not policy.is_finalized:
            raise HTTPException(status_code=409, detail="Only a finalized policy can satisfy an obligation link.")
    control = None
    if internal_control_definition_id:
        control = _same_tenant(session, InternalControlDefinition, internal_control_definition_id, decision.tenant_id)
    implementation = None
    if control_implementation_id:
        implementation = _same_tenant(session, ControlImplementation, control_implementation_id, decision.tenant_id)
        if control is None or implementation.internal_control_definition_id != control.internal_control_definition_id:
            raise HTTPException(status_code=409, detail="The implementation and control definition do not match.")
    requirement = ObligationRequirement(
        obligation_requirement_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        policy_version_id=policy.policy_version_id if policy else None,
        internal_control_definition_id=control.internal_control_definition_id if control else None,
        control_implementation_id=implementation.control_implementation_id if implementation else None,
        control_item_id=catalog_item.control_item_id if catalog_item else None,
        requirement_code=_text(requirement_code, "obligation requirement code"),
        requirement_title=_text(requirement_title, "obligation requirement title"),
        source_locator=source_locator.strip() if isinstance(source_locator, str) and source_locator.strip() else None,
        review_status="approved",
        mapping_rationale=_text(mapping_rationale, "obligation mapping rationale"),
        reviewed_by_actor=decision.actor_identifier,
        reviewed_at=_utc(),
        created_at=_utc(),
    )
    session.add(requirement)
    session.flush()
    record_audit_event(session, decision, "link_obligation_requirement", "obligation_requirement", requirement.obligation_requirement_id)
    return requirement


def record_regulatory_change(
    session: Session,
    decision: AuthorizationDecision,
    source_revision_id: str,
    change_code: str,
    change_summary: str,
    source_diff_reference: str,
    *,
    effective_at: datetime | None = None,
) -> RegulatoryChange:
    """Record a source-revision change without mutating earlier obligation history."""
    _require_compliance_purpose(decision)
    revision = _same_tenant(session, SourceRevision, source_revision_id, decision.tenant_id)
    code = _text(change_code, "regulatory change code")
    if session.query(RegulatoryChange).filter_by(tenant_id=decision.tenant_id, change_code=code).first():
        raise HTTPException(status_code=409, detail="That regulatory change code already exists.")
    change = RegulatoryChange(
        regulatory_change_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        source_revision_id=revision.source_revision_id,
        change_code=code,
        change_summary=_text(change_summary, "regulatory change summary"),
        source_diff_reference=_text(source_diff_reference, "source diff reference"),
        detected_at=_utc(),
        effective_at=_utc(effective_at) if effective_at else None,
        created_by_actor=decision.actor_identifier,
        created_at=_utc(),
    )
    session.add(change)
    session.flush()
    record_audit_event(session, decision, "record_regulatory_change", "regulatory_change", change.regulatory_change_id)
    return change


def assess_change_impact(
    session: Session,
    decision: AuthorizationDecision,
    regulatory_change_id: str,
    compliance_obligation_id: str,
    impact_status: str,
    impact_rationale: str,
    assigned_owner_reference: str,
    implementation_plan: str,
    reapproval_status: str,
    *,
    due_at: datetime | None = None,
) -> ChangeImpactAssessment:
    """Append an impact assessment with owner, due date, plan, and re-approval state."""
    _require_compliance_purpose(decision)
    change = _same_tenant(session, RegulatoryChange, regulatory_change_id, decision.tenant_id)
    obligation = _same_tenant(session, ComplianceObligation, compliance_obligation_id, decision.tenant_id)
    assessed_at = _utc()
    due = _utc(due_at) if due_at else None
    if due is not None and due < assessed_at:
        raise HTTPException(status_code=400, detail="The impact due date cannot be in the past.")
    number = (session.query(func.max(ChangeImpactAssessment.assessment_number)).filter_by(tenant_id=decision.tenant_id, regulatory_change_id=change.regulatory_change_id, compliance_obligation_id=obligation.compliance_obligation_id).scalar() or 0) + 1
    assessment = ChangeImpactAssessment(
        change_impact_assessment_id=uuid4().hex,
        tenant_id=decision.tenant_id,
        regulatory_change_id=change.regulatory_change_id,
        compliance_obligation_id=obligation.compliance_obligation_id,
        assessment_number=number,
        impact_status=_controlled(impact_status, {item.value for item in ImpactCode}, "impact status"),
        impact_rationale=_text(impact_rationale, "impact rationale"),
        assigned_owner_reference=_text(assigned_owner_reference, "impact owner"),
        due_at=due,
        implementation_plan=_text(implementation_plan, "implementation plan"),
        reapproval_status=_controlled(reapproval_status, {item.value for item in ReapprovalCode}, "re-approval status"),
        assessed_by_actor=decision.actor_identifier,
        assessed_at=assessed_at,
    )
    session.add(assessment)
    session.flush()
    record_audit_event(session, decision, "assess_change_impact", "change_impact_assessment", assessment.change_impact_assessment_id)
    return assessment


def obligation_next_action(code: str) -> str:
    """Return the officer action implied by one applicability state."""
    return {
        ApplicabilityCode.APPLICABLE.value: "Link the obligation to the approved policy and internal control test.",
        ApplicabilityCode.NOT_APPLICABLE.value: "Re-review the authorized not-applicable rationale by the next review date.",
        ApplicabilityCode.PARTIALLY_APPLICABLE.value: "Document the remaining scope and link compensating controls.",
        ApplicabilityCode.INHERITED.value: "Verify the inherited service boundary and supporting assurance.",
        ApplicabilityCode.COMPENSATING_CONTROL.value: "Review the compensating control and its operating evidence.",
        ApplicabilityCode.PENDING_REVIEW.value: "Assign an applicability reviewer and complete the decision.",
        ApplicabilityCode.UNKNOWN.value: "Decide applicability for the exact tenant scope.",
    }.get(code, "Decide applicability for the exact tenant scope.")


def list_obligation_worklist(
    session: Session,
    decision: AuthorizationDecision,
    *,
    as_of: datetime | None = None,
    upcoming_days: int = 30,
) -> list[ObligationWorkItem]:
    """Project same-tenant obligations into overdue, upcoming, or unqueued work."""
    _require_compliance_purpose(decision)
    if (
        isinstance(upcoming_days, bool)
        or not isinstance(upcoming_days, int)
        or upcoming_days < 0
        or upcoming_days > 3660
    ):
        raise HTTPException(status_code=400, detail="Upcoming days must be an integer between 0 and 3660.")
    current = _utc(as_of)
    horizon = current + timedelta(days=upcoming_days)
    items: list[ObligationWorkItem] = []
    obligations = session.query(ComplianceObligation).filter_by(tenant_id=decision.tenant_id).order_by(ComplianceObligation.effective_from).all()
    for obligation in obligations:
        latest_by_scope: dict[tuple[str, str], ApplicabilityDecision] = {}
        for candidate in (
            session.query(ApplicabilityDecision)
            .filter_by(tenant_id=decision.tenant_id, compliance_obligation_id=obligation.compliance_obligation_id)
            .order_by(ApplicabilityDecision.decided_at.desc())
            .all()
        ):
            scope = (candidate.scope_type, candidate.scope_reference)
            previous = latest_by_scope.get(scope)
            if previous is None or candidate.decided_at > previous.decided_at:
                latest_by_scope[scope] = candidate
        latest_decisions: list[ApplicabilityDecision | None] = list(latest_by_scope.values()) or [None]
        for latest in latest_decisions:
            review_at = latest.next_review_at if latest else None
            if review_at is not None and review_at < current:
                queue = "overdue"
            elif review_at is not None and review_at <= horizon:
                queue = "upcoming"
            else:
                queue = "none"
            code = latest.decision_code if latest else ApplicabilityCode.UNKNOWN.value
            items.append(
                ObligationWorkItem(
                    obligation,
                    code,
                    latest.scope_type if latest else obligation.scope_type,
                    latest.scope_reference if latest else obligation.scope_reference,
                    review_at,
                    queue,
                    obligation_next_action(code),
                )
            )
    return items
