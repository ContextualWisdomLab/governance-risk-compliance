"""Audit programs, engagements, sampling, findings, remediation, retest, and closure.

Every service function takes the request session and the declared
``AuthorizationDecision``. ``X-Actor-Id`` and ``X-Purpose`` are declarations for
audit context, not authentication: this slice stays a loopback-only developer
preview. Evidence is referenced by ``evidence_record_id`` only; evidence
plaintext is never copied into audit-management tables.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.audit_requests import (
    ActionCompletionRequest,
    AuditEngagementRequest,
    AuditProcedureRequest,
    AuditProgramRequest,
    EngagementCriterionRequest,
    EvidenceLinkRequest,
    FindingClosureRequest,
    FindingIssueRequest,
    FindingRetestRequest,
    FindingRevisionRequest,
    IndependenceDeclarationRequest,
    RemediationActionRequest,
    TeamMemberRequest,
)
from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.catalog import get_control_item
from cwl_grc.models import (
    AuditEngagement,
    AuditEvidenceLink,
    AuditFinding,
    AuditFindingRevision,
    AuditProcedure,
    AuditProgram,
    AuditSampleItem,
    ControlItem,
    EngagementCriterion,
    EngagementTeamMember,
    EvidenceRecord,
    FindingClosure,
    FindingRetest,
    IndependenceDeclaration,
    RemediationAction,
)

UNRESOLVED_FINDING_STATUSES = ("open", "remediation", "retest_failed")
"""Finding statuses that still need remediation, retest, or a closure decision."""

MAX_RISK_ACCEPTANCE_DAYS = 365
"""Upper bound on a placeholder risk-acceptance term, counted from today."""

ModelT = TypeVar("ModelT")


class AuditWorkflowError(Exception):
    """A rejected audit-management step that states the officer's next action."""

    def __init__(self, status_code: int, detail: str, next_action: str) -> None:
        """Store the HTTP status, the reason, and the next action."""
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.next_action = next_action


@dataclass(frozen=True)
class OverdueRemediation:
    """Open remediation actions and unresolved findings past their dates."""

    as_of: date
    overdue_actions: list[RemediationAction]
    overdue_findings: list[AuditFinding]


def _utc_now(now: datetime | None) -> datetime:
    """Return the injected time or the current naive UTC time."""
    return now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)


def _get_or_404(session: Session, model: type[ModelT], identifier: str, label: str) -> ModelT:
    """Load one row by primary key or reject without revealing other records."""
    row = session.get(model, identifier)
    if row is None:
        raise AuditWorkflowError(
            404,
            f"That {label} is not on file.",
            f"Check the {label} identifier and retry.",
        )
    return row


def _get_referenced(session: Session, model: type[ModelT], identifier: str) -> ModelT:
    """Load a row that a foreign key guarantees, failing loudly if the store is corrupt.

    Unlike ``assert``, this check survives ``python -O``.
    """
    row = session.get(model, identifier)
    if row is None:
        raise AuditWorkflowError(
            500,
            "A referenced audit record is missing; the store violates its foreign keys.",
            "Stop and ask an operator to check database integrity before retrying.",
        )
    return row


def _member(session: Session, engagement_id: str, actor: str) -> EngagementTeamMember | None:
    """Return the team membership of one actor, if any."""
    return (
        session.query(EngagementTeamMember)
        .filter_by(audit_engagement_id=engagement_id, auditor_actor=actor)
        .one_or_none()
    )


def _members(session: Session, engagement_id: str) -> list[EngagementTeamMember]:
    """Return the engagement team in a deterministic order."""
    return list(
        session.query(EngagementTeamMember)
        .filter_by(audit_engagement_id=engagement_id)
        .order_by(EngagementTeamMember.auditor_actor)
        .all()
    )


def _latest_declaration(
    session: Session,
    engagement_id: str,
    actor: str,
) -> IndependenceDeclaration | None:
    """Return the actor's current (highest-numbered) independence declaration."""
    return (
        session.query(IndependenceDeclaration)
        .filter_by(audit_engagement_id=engagement_id, auditor_actor=actor)
        .order_by(IndependenceDeclaration.declaration_number.desc())
        .first()
    )


def _require_member(session: Session, engagement_id: str, actor: str) -> EngagementTeamMember:
    """Reject an actor who is not on the engagement team."""
    member = _member(session, engagement_id, actor)
    if member is None:
        raise AuditWorkflowError(
            403,
            "Only engagement team members may perform this step.",
            "Ask the engagement lead to add you to the team, or hand the step to a team member.",
        )
    return member


def _require_non_conflicted(session: Session, engagement_id: str, actor: str) -> None:
    """Reject a team member whose latest declaration reports a conflict."""
    latest = _latest_declaration(session, engagement_id, actor)
    if latest is None or latest.has_conflict:
        raise AuditWorkflowError(
            409,
            "The auditor is not currently declared independent.",
            f"Record a conflict-free independence declaration for {actor}, "
            "or hand the step to an independent team member.",
        )


def _require_status(engagement: AuditEngagement, status: str, next_action: str) -> None:
    """Reject a step outside the required engagement status."""
    if engagement.engagement_status != status:
        raise AuditWorkflowError(
            409,
            f"The engagement is {engagement.engagement_status}; this step needs {status}.",
            next_action,
        )


def _require_lead(engagement: AuditEngagement, actor: str) -> None:
    """Reject anyone other than the engagement's lead auditor."""
    if actor != engagement.lead_auditor_actor:
        raise AuditWorkflowError(
            403,
            "Only the engagement lead auditor may perform this step.",
            f"Ask the lead auditor {engagement.lead_auditor_actor} to perform this step.",
        )


def _require_planner(session: Session, engagement: AuditEngagement, actor: str) -> None:
    """Reject anyone other than the program authority or the engagement lead."""
    program = _get_referenced(session, AuditProgram, engagement.audit_program_id)
    if actor not in {program.audit_authority_actor, engagement.lead_auditor_actor}:
        raise AuditWorkflowError(
            403,
            "Only the audit authority or the engagement lead may plan this engagement.",
            "Ask the audit authority or the lead auditor to make this planning change.",
        )


def _require_fieldwork_auditor(
    session: Session,
    engagement: AuditEngagement,
    actor: str,
) -> None:
    """Apply the fieldwork order: status, then membership, then independence."""
    _require_status(
        engagement,
        "fieldwork",
        "Record procedures, evidence links, and findings only while the engagement is in fieldwork.",
    )
    _require_member(session, engagement.audit_engagement_id, actor)
    _require_non_conflicted(session, engagement.audit_engagement_id, actor)


def _engagement_criterion(
    session: Session,
    engagement_id: str,
    criterion_id: str,
) -> EngagementCriterion:
    """Return a criterion that belongs to the given engagement, else 404."""
    criterion = session.get(EngagementCriterion, criterion_id)
    if criterion is None or criterion.audit_engagement_id != engagement_id:
        raise AuditWorkflowError(
            404,
            "That engagement criterion is not on file for this engagement.",
            "Choose one of this engagement's criteria.",
        )
    return criterion


def _evidence(session: Session, evidence_record_id: str) -> EvidenceRecord:
    """Return an existing evidence record, else 404."""
    return _get_or_404(session, EvidenceRecord, evidence_record_id, "evidence record")


def _require_unresolved(finding: AuditFinding) -> None:
    """Reject changes to a closed or risk-accepted finding."""
    if finding.finding_status not in UNRESOLVED_FINDING_STATUSES:
        raise AuditWorkflowError(
            409,
            f"The finding is already {finding.finding_status}.",
            "Raise a new finding if the condition recurs.",
        )


def _actions(session: Session, finding_id: str) -> list[RemediationAction]:
    """Return a finding's remediation actions in creation order."""
    return list(
        session.query(RemediationAction)
        .filter_by(audit_finding_id=finding_id)
        .order_by(RemediationAction.created_at, RemediationAction.remediation_action_id)
        .all()
    )


def _latest_retest(session: Session, finding_id: str) -> FindingRetest | None:
    """Return the most recent retest of a finding, if any."""
    return (
        session.query(FindingRetest)
        .filter_by(audit_finding_id=finding_id)
        .order_by(FindingRetest.retest_number.desc())
        .first()
    )


def select_sample_ordinals(
    method: str,
    population_size: int,
    sample_size: int,
    seed: int | None,
    ordinals: list[int] | None,
) -> list[int]:
    """Return the sorted, reproducible 1-based sample for one selection method."""
    if sample_size < 1 or population_size < 1 or sample_size > population_size:
        raise AuditWorkflowError(
            400,
            "The sample size must be between 1 and the population size.",
            "Reduce the sample size or correct the population size.",
        )
    if method == "seeded_random":
        if seed is None or ordinals is not None:
            raise AuditWorkflowError(
                400,
                "Seeded random selection needs a seed and no explicit ordinals.",
                "State the selection seed and remove the explicit ordinals.",
            )
        return sorted(random.Random(seed).sample(range(1, population_size + 1), sample_size))
    if method == "full_population":
        if sample_size != population_size or seed is not None or ordinals is not None:
            raise AuditWorkflowError(
                400,
                "Full-population testing covers every item without a seed or ordinals.",
                "Set the sample size to the population size and remove the seed and ordinals.",
            )
        return list(range(1, population_size + 1))
    if method != "judgmental":
        raise AuditWorkflowError(
            400,
            "Unknown selection method.",
            "Choose seeded_random, judgmental, or full_population.",
        )
    if ordinals is None or seed is not None:
        raise AuditWorkflowError(
            400,
            "Judgmental selection needs explicit ordinals and no seed.",
            "List the population ordinals you selected and remove the seed.",
        )
    if (
        len(set(ordinals)) != len(ordinals)
        or len(ordinals) != sample_size
        or any(ordinal < 1 or ordinal > population_size for ordinal in ordinals)
    ):
        raise AuditWorkflowError(
            400,
            "Judgmental ordinals must be unique, within the population, and match the sample size.",
            "List exactly sample_size unique ordinals between 1 and the population size.",
        )
    return sorted(ordinals)


def create_program(
    session: Session,
    decision: AuthorizationDecision,
    request: AuditProgramRequest,
    now: datetime | None = None,
) -> AuditProgram:
    """Plan a draft audit program for the named audit authority to approve."""
    if request.period_end < request.period_start:
        raise AuditWorkflowError(
            400,
            "The program period ends before it starts.",
            "Correct the program period so the end date follows the start date.",
        )
    program = AuditProgram(
        audit_program_id=uuid4().hex,
        program_title=request.program_title,
        period_start=request.period_start,
        period_end=request.period_end,
        risk_rationale=request.risk_rationale,
        audit_authority_actor=request.audit_authority_actor,
        created_by_actor=decision.actor_identifier,
        created_at=_utc_now(now),
        program_status="draft",
    )
    session.add(program)
    record_audit_event(session, decision, "create_audit_program", "audit_program", program.audit_program_id)
    session.flush()
    return program


def approve_program(
    session: Session,
    decision: AuthorizationDecision,
    program_id: str,
    now: datetime | None = None,
) -> AuditProgram:
    """Approve a draft program by its named authority, who must not be its planner."""
    program = _get_or_404(session, AuditProgram, program_id, "audit program")
    actor = decision.actor_identifier
    if actor != program.audit_authority_actor or actor == program.created_by_actor:
        raise AuditWorkflowError(
            403,
            "Only the named audit authority, who did not plan the program, may approve it.",
            f"Ask the audit authority {program.audit_authority_actor} to approve this program; "
            "a self-planned program needs a separate planner.",
        )
    if program.program_status == "approved":
        raise AuditWorkflowError(
            409,
            "The audit program is already approved.",
            "Plan engagements under the approved program.",
        )
    program.program_status = "approved"
    program.approved_by_actor = actor
    program.approved_at = _utc_now(now)
    record_audit_event(session, decision, "approve_audit_program", "audit_program", program_id)
    session.flush()
    return program


def create_engagement(
    session: Session,
    decision: AuthorizationDecision,
    program_id: str,
    request: AuditEngagementRequest,
    now: datetime | None = None,
) -> AuditEngagement:
    """Plan an engagement inside the period of an approved program."""
    program = _get_or_404(session, AuditProgram, program_id, "audit program")
    if decision.actor_identifier != program.audit_authority_actor:
        raise AuditWorkflowError(
            403,
            "Only the program's audit authority may plan engagements.",
            f"Ask the audit authority {program.audit_authority_actor} to plan this engagement.",
        )
    if program.program_status != "approved":
        raise AuditWorkflowError(
            409,
            "The audit program is not approved yet.",
            "Have the audit authority approve the program before planning engagements.",
        )
    if (
        request.period_end < request.period_start
        or request.period_start < program.period_start
        or request.period_end > program.period_end
    ):
        raise AuditWorkflowError(
            400,
            "The engagement period must be ordered and inside the program period.",
            f"Choose an engagement period between {program.period_start.isoformat()} "
            f"and {program.period_end.isoformat()}.",
        )
    engagement = AuditEngagement(
        audit_engagement_id=uuid4().hex,
        audit_program_id=program_id,
        engagement_title=request.engagement_title,
        scope_statement=request.scope_statement,
        period_start=request.period_start,
        period_end=request.period_end,
        lead_auditor_actor=request.lead_auditor_actor,
        engagement_status="planned",
        created_at=_utc_now(now),
    )
    session.add(engagement)
    record_audit_event(
        session, decision, "create_audit_engagement", "audit_engagement", engagement.audit_engagement_id
    )
    session.flush()
    return engagement


def add_criterion(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    request: EngagementCriterionRequest,
) -> EngagementCriterion:
    """Add one official catalog control as a criterion of a planned engagement."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_planner(session, engagement, decision.actor_identifier)
    _require_status(engagement, "planned", "Change criteria only before fieldwork starts.")
    control = get_control_item(session, request.framework, request.catalog_identifier)
    if control is None:
        raise AuditWorkflowError(
            404,
            "That official control is not on file in the catalog.",
            "Choose an official identifier from the seeded control catalog.",
        )
    duplicate = (
        session.query(EngagementCriterion)
        .filter_by(audit_engagement_id=engagement_id, control_item_id=control.control_item_id)
        .one_or_none()
    )
    if duplicate is not None:
        raise AuditWorkflowError(
            409,
            "That control is already a criterion of this engagement.",
            "Add a different official control, or start the engagement.",
        )
    criterion = EngagementCriterion(
        engagement_criterion_id=uuid4().hex,
        audit_engagement_id=engagement_id,
        control_item_id=control.control_item_id,
        internal_control_reference=request.internal_control_reference,
    )
    session.add(criterion)
    record_audit_event(
        session,
        decision,
        "add_engagement_criterion",
        "engagement_criterion",
        criterion.engagement_criterion_id,
    )
    session.flush()
    return criterion


def add_team_member(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    request: TeamMemberRequest,
) -> EngagementTeamMember:
    """Assign one competent auditor to a planned engagement."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_planner(session, engagement, decision.actor_identifier)
    _require_status(engagement, "planned", "Change the team only before fieldwork starts.")
    if _member(session, engagement_id, request.auditor_actor) is not None:
        raise AuditWorkflowError(
            409,
            "That auditor is already on the engagement team.",
            "Add a different auditor, or record independence declarations.",
        )
    member = EngagementTeamMember(
        engagement_team_member_id=uuid4().hex,
        audit_engagement_id=engagement_id,
        auditor_actor=request.auditor_actor,
        team_role=request.team_role,
        competence_statement=request.competence_statement,
    )
    session.add(member)
    record_audit_event(
        session,
        decision,
        "add_engagement_team_member",
        "engagement_team_member",
        member.engagement_team_member_id,
    )
    session.flush()
    return member


def declare_independence(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    request: IndependenceDeclarationRequest,
    now: datetime | None = None,
) -> IndependenceDeclaration:
    """Append the declaring team member's next immutable independence declaration."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    actor = decision.actor_identifier
    _require_member(session, engagement_id, actor)
    if engagement.engagement_status == "closed":
        raise AuditWorkflowError(
            409,
            "The engagement is closed.",
            "Record independence declarations on an open engagement.",
        )
    latest = _latest_declaration(session, engagement_id, actor)
    declaration = IndependenceDeclaration(
        independence_declaration_id=uuid4().hex,
        audit_engagement_id=engagement_id,
        auditor_actor=actor,
        declaration_number=1 if latest is None else latest.declaration_number + 1,
        has_conflict=request.has_conflict,
        declaration_statement=request.declaration_statement,
        declared_at=_utc_now(now),
    )
    session.add(declaration)
    record_audit_event(
        session,
        decision,
        "declare_independence",
        "independence_declaration",
        declaration.independence_declaration_id,
    )
    session.flush()
    return declaration


def start_engagement(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    now: datetime | None = None,
) -> AuditEngagement:
    """Move a fully staffed, independent, criteria-bearing engagement into fieldwork."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_lead(engagement, decision.actor_identifier)
    _require_status(engagement, "planned", "The engagement has already started.")
    if session.query(EngagementCriterion).filter_by(audit_engagement_id=engagement_id).count() == 0:
        raise AuditWorkflowError(
            409,
            "The engagement has no audit criteria.",
            "Add at least one official catalog criterion before starting fieldwork.",
        )
    members = _members(session, engagement_id)
    leads = [member.auditor_actor for member in members if member.team_role == "lead"]
    if leads != [engagement.lead_auditor_actor]:
        raise AuditWorkflowError(
            409,
            "The team needs exactly one lead, who is the engagement's lead auditor.",
            f"Assign {engagement.lead_auditor_actor} as the only team member with the lead role.",
        )
    if not any(member.team_role == "supervisor" for member in members):
        raise AuditWorkflowError(
            409,
            "The team has no supervisor.",
            "Add a supervisor to the engagement team before starting fieldwork.",
        )
    for member in members:
        latest = _latest_declaration(session, engagement_id, member.auditor_actor)
        if latest is None:
            raise AuditWorkflowError(
                409,
                "A team member has not declared independence.",
                f"Ask {member.auditor_actor} to record an independence declaration.",
            )
        if latest.has_conflict:
            raise AuditWorkflowError(
                409,
                "A team member has a declared conflict of interest.",
                f"Replace {member.auditor_actor} or record a conflict-free declaration "
                "before starting fieldwork.",
            )
    engagement.engagement_status = "fieldwork"
    engagement.started_at = _utc_now(now)
    record_audit_event(session, decision, "start_audit_engagement", "audit_engagement", engagement_id)
    session.flush()
    return engagement


def create_procedure(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    request: AuditProcedureRequest,
    now: datetime | None = None,
) -> tuple[AuditProcedure, list[int]]:
    """Document a procedure and persist its reproducible sample selection."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_fieldwork_auditor(session, engagement, decision.actor_identifier)
    criterion = _engagement_criterion(session, engagement_id, request.engagement_criterion_id)
    ordinals = select_sample_ordinals(
        request.selection_method,
        request.population_size,
        request.sample_size,
        request.selection_seed,
        request.selected_ordinals,
    )
    procedure = AuditProcedure(
        audit_procedure_id=uuid4().hex,
        audit_engagement_id=engagement_id,
        engagement_criterion_id=criterion.engagement_criterion_id,
        procedure_description=request.procedure_description,
        population_description=request.population_description,
        population_size=request.population_size,
        selection_method=request.selection_method,
        sample_size=request.sample_size,
        selection_seed=request.selection_seed,
        created_by_actor=decision.actor_identifier,
        created_at=_utc_now(now),
    )
    session.add(procedure)
    session.flush()
    for ordinal in ordinals:
        session.add(
            AuditSampleItem(
                audit_sample_item_id=uuid4().hex,
                audit_procedure_id=procedure.audit_procedure_id,
                population_ordinal=ordinal,
            )
        )
    record_audit_event(
        session, decision, "create_audit_procedure", "audit_procedure", procedure.audit_procedure_id
    )
    session.flush()
    return procedure, ordinals


def link_evidence(
    session: Session,
    decision: AuthorizationDecision,
    procedure_id: str,
    request: EvidenceLinkRequest,
    now: datetime | None = None,
) -> AuditEvidenceLink:
    """Reference existing evidence from a procedure or one of its sample items."""
    procedure = _get_or_404(session, AuditProcedure, procedure_id, "audit procedure")
    engagement = _get_referenced(session, AuditEngagement, procedure.audit_engagement_id)
    _require_fieldwork_auditor(session, engagement, decision.actor_identifier)
    evidence = _evidence(session, request.evidence_record_id)
    sample_item_id: str | None = None
    if request.population_ordinal is not None:
        item = (
            session.query(AuditSampleItem)
            .filter_by(audit_procedure_id=procedure_id, population_ordinal=request.population_ordinal)
            .one_or_none()
        )
        if item is None:
            raise AuditWorkflowError(
                404,
                "That population ordinal is not on file in this procedure's sample.",
                "Link evidence to one of the procedure's selected ordinals.",
            )
        sample_item_id = item.audit_sample_item_id
    link = AuditEvidenceLink(
        audit_evidence_link_id=uuid4().hex,
        evidence_record_id=evidence.evidence_record_id,
        audit_procedure_id=procedure_id if sample_item_id is None else None,
        audit_sample_item_id=sample_item_id,
        linked_by_actor=decision.actor_identifier,
        linked_at=_utc_now(now),
    )
    session.add(link)
    record_audit_event(
        session, decision, "link_audit_evidence", "audit_evidence_link", link.audit_evidence_link_id
    )
    session.flush()
    return link


def _write_revision(
    session: Session,
    decision: AuthorizationDecision,
    finding_id: str,
    revision_number: int,
    request: FindingIssueRequest | FindingRevisionRequest,
    criterion_id: str,
    revised_at: datetime,
) -> AuditFindingRevision:
    """Append one immutable finding edition."""
    revision = AuditFindingRevision(
        audit_finding_revision_id=uuid4().hex,
        audit_finding_id=finding_id,
        revision_number=revision_number,
        engagement_criterion_id=criterion_id,
        condition_statement=request.condition_statement,
        cause_statement=request.cause_statement,
        effect_statement=request.effect_statement,
        severity_rating=request.severity_rating,
        rating_rationale=request.rating_rationale,
        recommendation_text=request.recommendation_text,
        revised_by_actor=decision.actor_identifier,
        revised_at=revised_at,
    )
    session.add(revision)
    return revision


def issue_finding(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
    request: FindingIssueRequest,
    now: datetime | None = None,
) -> AuditFinding:
    """Issue a finding with its first revision and an independent remediation owner."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_fieldwork_auditor(session, engagement, decision.actor_identifier)
    criterion = _engagement_criterion(session, engagement_id, request.engagement_criterion_id)
    if _member(session, engagement_id, request.remediation_owner_actor) is not None:
        raise AuditWorkflowError(
            409,
            "An engagement team member cannot own remediation of its own finding.",
            "Name a remediation owner from the audited function, outside the audit team.",
        )
    created_at = _utc_now(now)
    finding = AuditFinding(
        audit_finding_id=uuid4().hex,
        audit_engagement_id=engagement_id,
        finding_status="open",
        remediation_owner_actor=request.remediation_owner_actor,
        target_date=request.target_date,
        current_revision_number=1,
        created_at=created_at,
    )
    session.add(finding)
    session.flush()
    _write_revision(
        session, decision, finding.audit_finding_id, 1, request,
        criterion.engagement_criterion_id, created_at,
    )
    record_audit_event(session, decision, "issue_audit_finding", "audit_finding", finding.audit_finding_id)
    session.flush()
    return finding


def revise_finding(
    session: Session,
    decision: AuthorizationDecision,
    finding_id: str,
    request: FindingRevisionRequest,
    now: datetime | None = None,
) -> AuditFinding:
    """Append the next finding edition only when the caller holds the current revision."""
    finding = _get_or_404(session, AuditFinding, finding_id, "audit finding")
    _require_member(session, finding.audit_engagement_id, decision.actor_identifier)
    _require_unresolved(finding)
    criterion = _engagement_criterion(
        session, finding.audit_engagement_id, request.engagement_criterion_id
    )
    next_number = request.expected_revision + 1
    result = session.execute(
        update(AuditFinding)
        .where(
            AuditFinding.audit_finding_id == finding_id,
            AuditFinding.current_revision_number == request.expected_revision,
        )
        .values(current_revision_number=next_number)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise AuditWorkflowError(
            409,
            "The finding changed since you loaded it.",
            "Reload the finding and revise its current revision.",
        )
    finding.current_revision_number = next_number
    _write_revision(
        session, decision, finding_id, next_number, request,
        criterion.engagement_criterion_id, _utc_now(now),
    )
    record_audit_event(session, decision, "revise_audit_finding", "audit_finding", finding_id)
    session.flush()
    return finding


def create_remediation_action(
    session: Session,
    decision: AuthorizationDecision,
    finding_id: str,
    request: RemediationActionRequest,
    now: datetime | None = None,
) -> RemediationAction:
    """Record a remediation action by the finding's remediation owner."""
    finding = _get_or_404(session, AuditFinding, finding_id, "audit finding")
    if decision.actor_identifier != finding.remediation_owner_actor:
        raise AuditWorkflowError(
            403,
            "Only the finding's remediation owner may record remediation actions.",
            f"Ask the remediation owner {finding.remediation_owner_actor} to record the action.",
        )
    _require_unresolved(finding)
    if _member(session, finding.audit_engagement_id, request.owner_actor) is not None:
        raise AuditWorkflowError(
            409,
            "An engagement team member cannot own a remediation action.",
            "Assign the action to someone in the audited function, outside the audit team.",
        )
    latest = _latest_retest(session, finding_id)
    if latest is not None and latest.retest_result == "passed":
        raise AuditWorkflowError(
            409,
            "The latest retest passed; the finding awaits closure.",
            "Ask the engagement lead or a supervisor to close the finding.",
        )
    action = RemediationAction(
        remediation_action_id=uuid4().hex,
        audit_finding_id=finding_id,
        action_description=request.action_description,
        owner_actor=request.owner_actor,
        due_date=request.due_date,
        action_status="open",
        created_by_actor=decision.actor_identifier,
        created_at=_utc_now(now),
    )
    session.add(action)
    finding.finding_status = "remediation"
    record_audit_event(
        session, decision, "create_remediation_action", "remediation_action", action.remediation_action_id
    )
    session.flush()
    return action


def complete_remediation_action(
    session: Session,
    decision: AuthorizationDecision,
    action_id: str,
    request: ActionCompletionRequest,
    now: datetime | None = None,
) -> RemediationAction:
    """Complete a remediation action by its owner with an existing evidence record."""
    action = _get_or_404(session, RemediationAction, action_id, "remediation action")
    if decision.actor_identifier != action.owner_actor:
        raise AuditWorkflowError(
            403,
            "Only the action owner may complete this remediation action.",
            f"Ask the action owner {action.owner_actor} to complete it.",
        )
    if action.action_status == "completed":
        raise AuditWorkflowError(
            409,
            "The remediation action is already completed.",
            "Ask an independent auditor to retest the finding.",
        )
    evidence = _evidence(session, request.completion_evidence_record_id)
    action.action_status = "completed"
    action.completed_at = _utc_now(now)
    action.completion_evidence_record_id = evidence.evidence_record_id
    record_audit_event(
        session, decision, "complete_remediation_action", "remediation_action", action_id
    )
    session.flush()
    return action


def record_retest(
    session: Session,
    decision: AuthorizationDecision,
    finding_id: str,
    request: FindingRetestRequest,
    now: datetime | None = None,
) -> tuple[FindingRetest, AuditFinding]:
    """Record an independent retest after every remediation action is completed."""
    finding = _get_or_404(session, AuditFinding, finding_id, "audit finding")
    _require_unresolved(finding)
    actor = decision.actor_identifier
    actions = _actions(session, finding_id)
    if (
        _member(session, finding.audit_engagement_id, actor) is None
        or actor == finding.remediation_owner_actor
        or any(actor == action.owner_actor for action in actions)
    ):
        raise AuditWorkflowError(
            403,
            "Only an independent team member may retest remediation.",
            "Ask an engagement team member who owns no remediation to retest.",
        )
    if not actions:
        raise AuditWorkflowError(
            409,
            "The finding has no remediation actions to retest.",
            "Ask the remediation owner to record a remediation action before retesting.",
        )
    open_ids = [a.remediation_action_id for a in actions if a.action_status != "completed"]
    if open_ids:
        raise AuditWorkflowError(
            409,
            "Some remediation actions are still open.",
            "Complete remediation actions " + ", ".join(open_ids) + " before retesting.",
        )
    evidence = _evidence(session, request.evidence_record_id)
    _require_non_conflicted(session, finding.audit_engagement_id, actor)
    latest = _latest_retest(session, finding_id)
    retest = FindingRetest(
        finding_retest_id=uuid4().hex,
        audit_finding_id=finding_id,
        retest_number=1 if latest is None else latest.retest_number + 1,
        retest_actor=actor,
        procedure_description=request.procedure_description,
        retest_result=request.retest_result,
        effectiveness_conclusion=request.effectiveness_conclusion,
        evidence_record_id=evidence.evidence_record_id,
        tested_at=_utc_now(now),
    )
    session.add(retest)
    finding.finding_status = "remediation" if request.retest_result == "passed" else "retest_failed"
    record_audit_event(session, decision, "record_finding_retest", "finding_retest", retest.finding_retest_id)
    session.flush()
    return retest, finding


def close_finding(
    session: Session,
    decision: AuthorizationDecision,
    finding_id: str,
    request: FindingClosureRequest,
    today: date | None = None,
    now: datetime | None = None,
) -> tuple[FindingClosure, AuditFinding]:
    """Close a finding on a passing retest, or record a bounded risk acceptance.

    Issue #13 governed risk acceptance is not merged. A ``risk_accepted`` closure
    is a bounded placeholder decision record: a different authority, an expiry
    after today and at most 365 days ahead, and no claim of a governed
    risk-register workflow.
    """
    finding = _get_or_404(session, AuditFinding, finding_id, "audit finding")
    actor = decision.actor_identifier
    member = _member(session, finding.audit_engagement_id, actor)
    if member is None or member.team_role not in {"lead", "supervisor"}:
        raise AuditWorkflowError(
            403,
            "Only the engagement lead or a supervisor may close a finding.",
            "Ask the engagement lead or a supervisor to close the finding.",
        )
    _require_unresolved(finding)
    retest_id: str | None = None
    status = "closed"
    if request.closure_basis == "retest_passed":
        latest = _latest_retest(session, finding_id)
        if latest is None or latest.retest_result != "passed":
            raise AuditWorkflowError(
                409,
                "The latest retest has not passed.",
                "Record a passing independent retest before closing the finding.",
            )
        retest_id = latest.finding_retest_id
    else:
        authority = request.acceptance_authority_actor
        expires = request.acceptance_expires_on
        if authority is None or expires is None:
            raise AuditWorkflowError(
                400,
                "Risk acceptance needs an acceptance authority and an expiry date.",
                "Name the acceptance authority and the acceptance expiry date.",
            )
        owners = {finding.remediation_owner_actor}
        owners.update(action.owner_actor for action in _actions(session, finding_id))
        if authority in owners or _member(session, finding.audit_engagement_id, authority):
            raise AuditWorkflowError(
                409,
                "The acceptance authority must be independent of remediation and the audit team.",
                "Name an acceptance authority who owns no remediation and is not on the team.",
            )
        current = today if today is not None else date.today()
        if not current < expires <= current + timedelta(days=MAX_RISK_ACCEPTANCE_DAYS):
            raise AuditWorkflowError(
                400,
                "Risk acceptance must expire after today and within 365 days.",
                "Choose an expiry date after today and at most 365 days ahead.",
            )
        status = "risk_accepted"
    closure = FindingClosure(
        finding_closure_id=uuid4().hex,
        audit_finding_id=finding_id,
        closure_basis=request.closure_basis,
        finding_retest_id=retest_id,
        closing_actor=actor,
        acceptance_authority_actor=(
            request.acceptance_authority_actor if status == "risk_accepted" else None
        ),
        acceptance_expires_on=request.acceptance_expires_on if status == "risk_accepted" else None,
        closure_rationale=request.closure_rationale,
        closed_at=_utc_now(now),
    )
    session.add(closure)
    finding.finding_status = status
    record_audit_event(session, decision, "close_audit_finding", "audit_finding", finding_id)
    session.flush()
    return closure, finding


def move_to_reporting(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
) -> AuditEngagement:
    """Move fieldwork to reporting once every procedure is documented with evidence."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_lead(engagement, decision.actor_identifier)
    _require_status(engagement, "fieldwork", "Move to reporting only from fieldwork.")
    procedures = (
        session.query(AuditProcedure).filter_by(audit_engagement_id=engagement_id).all()
    )
    undocumented = [
        procedure.audit_procedure_id
        for procedure in procedures
        if not _procedure_links(session, procedure.audit_procedure_id)
    ]
    if not procedures or undocumented:
        raise AuditWorkflowError(
            409,
            "Every engagement needs at least one procedure, each with linked evidence.",
            "Document at least one procedure and link evidence to every procedure "
            "before reporting.",
        )
    engagement.engagement_status = "reporting"
    record_audit_event(
        session, decision, "move_engagement_to_reporting", "audit_engagement", engagement_id
    )
    session.flush()
    return engagement


def close_engagement(
    session: Session,
    decision: AuthorizationDecision,
    engagement_id: str,
) -> AuditEngagement:
    """Close a reported engagement once no finding is unresolved."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    _require_lead(engagement, decision.actor_identifier)
    _require_status(engagement, "reporting", "Move the engagement to reporting before closing it.")
    unresolved = (
        session.query(AuditFinding)
        .filter(
            AuditFinding.audit_engagement_id == engagement_id,
            AuditFinding.finding_status.in_(UNRESOLVED_FINDING_STATUSES),
        )
        .count()
    )
    if unresolved:
        raise AuditWorkflowError(
            409,
            f"{unresolved} finding(s) are still unresolved.",
            "Close or risk-accept every open finding before closing the engagement.",
        )
    engagement.engagement_status = "closed"
    record_audit_event(session, decision, "close_audit_engagement", "audit_engagement", engagement_id)
    session.flush()
    return engagement


def list_overdue_remediation(session: Session, today: date | None = None) -> OverdueRemediation:
    """List open actions and unresolved findings whose dates fall before ``as_of``."""
    as_of = today if today is not None else date.today()
    actions = (
        session.query(RemediationAction)
        .join(AuditFinding, AuditFinding.audit_finding_id == RemediationAction.audit_finding_id)
        .filter(
            RemediationAction.action_status == "open",
            RemediationAction.due_date < as_of,
            AuditFinding.finding_status.in_(UNRESOLVED_FINDING_STATUSES),
        )
        .order_by(RemediationAction.due_date, RemediationAction.remediation_action_id)
        .all()
    )
    findings = (
        session.query(AuditFinding)
        .filter(
            AuditFinding.finding_status.in_(UNRESOLVED_FINDING_STATUSES),
            AuditFinding.target_date < as_of,
        )
        .order_by(AuditFinding.target_date, AuditFinding.audit_finding_id)
        .all()
    )
    return OverdueRemediation(as_of=as_of, overdue_actions=list(actions), overdue_findings=list(findings))


def _procedure_links(session: Session, procedure_id: str) -> list[AuditEvidenceLink]:
    """Return procedure-level and sample-level evidence links of one procedure."""
    sample_ids = [
        row[0]
        for row in session.query(AuditSampleItem.audit_sample_item_id)
        .filter_by(audit_procedure_id=procedure_id)
        .all()
    ]
    return list(
        session.query(AuditEvidenceLink)
        .filter(
            (AuditEvidenceLink.audit_procedure_id == procedure_id)
            | (AuditEvidenceLink.audit_sample_item_id.in_(sample_ids))
        )
        .order_by(AuditEvidenceLink.linked_at, AuditEvidenceLink.audit_evidence_link_id)
        .all()
    )


def _sample_ordinals(session: Session, procedure_id: str) -> list[int]:
    """Return the stored, sorted sample ordinals of one procedure."""
    return [
        row[0]
        for row in session.query(AuditSampleItem.population_ordinal)
        .filter_by(audit_procedure_id=procedure_id)
        .order_by(AuditSampleItem.population_ordinal)
        .all()
    ]


def serialize_program(program: AuditProgram) -> dict[str, Any]:
    """Serialize one audit program."""
    return {
        "audit_program_id": program.audit_program_id,
        "program_title": program.program_title,
        "period_start": program.period_start,
        "period_end": program.period_end,
        "risk_rationale": program.risk_rationale,
        "audit_authority_actor": program.audit_authority_actor,
        "created_by_actor": program.created_by_actor,
        "approved_by_actor": program.approved_by_actor,
        "program_status": program.program_status,
    }


def serialize_engagement(engagement: AuditEngagement) -> dict[str, Any]:
    """Serialize the header of one audit engagement."""
    return {
        "audit_engagement_id": engagement.audit_engagement_id,
        "audit_program_id": engagement.audit_program_id,
        "engagement_title": engagement.engagement_title,
        "scope_statement": engagement.scope_statement,
        "period_start": engagement.period_start,
        "period_end": engagement.period_end,
        "lead_auditor_actor": engagement.lead_auditor_actor,
        "engagement_status": engagement.engagement_status,
    }


def serialize_criterion(session: Session, criterion: EngagementCriterion) -> dict[str, Any]:
    """Serialize one criterion with its official catalog identity."""
    control = _get_referenced(session, ControlItem, criterion.control_item_id)
    return {
        "engagement_criterion_id": criterion.engagement_criterion_id,
        "framework": control.framework_key,
        "catalog_identifier": control.catalog_identifier,
        "control_title": control.control_title,
        "internal_control_reference": criterion.internal_control_reference,
    }


def serialize_team_member(member: EngagementTeamMember) -> dict[str, Any]:
    """Serialize one engagement team member."""
    return {
        "engagement_team_member_id": member.engagement_team_member_id,
        "auditor_actor": member.auditor_actor,
        "team_role": member.team_role,
        "competence_statement": member.competence_statement,
    }


def serialize_declaration(declaration: IndependenceDeclaration) -> dict[str, Any]:
    """Serialize one independence declaration."""
    return {
        "independence_declaration_id": declaration.independence_declaration_id,
        "auditor_actor": declaration.auditor_actor,
        "declaration_number": declaration.declaration_number,
        "has_conflict": declaration.has_conflict,
        "declaration_statement": declaration.declaration_statement,
        "declared_at": declaration.declared_at,
    }


def serialize_procedure(
    procedure: AuditProcedure,
    ordinals: list[int],
    links: list[AuditEvidenceLink] | None = None,
) -> dict[str, Any]:
    """Serialize one procedure with its sample and, when given, its evidence links."""
    payload: dict[str, Any] = {
        "audit_procedure_id": procedure.audit_procedure_id,
        "engagement_criterion_id": procedure.engagement_criterion_id,
        "procedure_description": procedure.procedure_description,
        "population_description": procedure.population_description,
        "population_size": procedure.population_size,
        "selection_method": procedure.selection_method,
        "sample_size": procedure.sample_size,
        "selection_seed": procedure.selection_seed,
        "selected_ordinals": ordinals,
    }
    if links is not None:
        payload["evidence_links"] = [serialize_evidence_link(link) for link in links]
    return payload


def serialize_evidence_link(link: AuditEvidenceLink) -> dict[str, Any]:
    """Serialize one evidence reference without any evidence plaintext."""
    return {
        "audit_evidence_link_id": link.audit_evidence_link_id,
        "evidence_record_id": link.evidence_record_id,
        "audit_procedure_id": link.audit_procedure_id,
        "audit_sample_item_id": link.audit_sample_item_id,
        "linked_by_actor": link.linked_by_actor,
    }


def serialize_finding_summary(finding: AuditFinding) -> dict[str, Any]:
    """Serialize a finding's identity, status, and revision counter."""
    return {
        "audit_finding_id": finding.audit_finding_id,
        "audit_engagement_id": finding.audit_engagement_id,
        "finding_status": finding.finding_status,
        "remediation_owner_actor": finding.remediation_owner_actor,
        "target_date": finding.target_date,
        "current_revision_number": finding.current_revision_number,
    }


def serialize_revision(revision: AuditFindingRevision) -> dict[str, Any]:
    """Serialize one immutable finding edition."""
    return {
        "revision_number": revision.revision_number,
        "engagement_criterion_id": revision.engagement_criterion_id,
        "condition_statement": revision.condition_statement,
        "cause_statement": revision.cause_statement,
        "effect_statement": revision.effect_statement,
        "severity_rating": revision.severity_rating,
        "rating_rationale": revision.rating_rationale,
        "recommendation_text": revision.recommendation_text,
        "revised_by_actor": revision.revised_by_actor,
        "revised_at": revision.revised_at,
    }


def serialize_action(action: RemediationAction, finding_status: str | None = None) -> dict[str, Any]:
    """Serialize one remediation action, optionally with its finding status."""
    payload: dict[str, Any] = {
        "remediation_action_id": action.remediation_action_id,
        "audit_finding_id": action.audit_finding_id,
        "action_description": action.action_description,
        "owner_actor": action.owner_actor,
        "due_date": action.due_date,
        "action_status": action.action_status,
        "completed_at": action.completed_at,
        "completion_evidence_record_id": action.completion_evidence_record_id,
    }
    if finding_status is not None:
        payload["finding_status"] = finding_status
    return payload


def serialize_retest(retest: FindingRetest) -> dict[str, Any]:
    """Serialize one immutable retest."""
    return {
        "finding_retest_id": retest.finding_retest_id,
        "retest_number": retest.retest_number,
        "retest_actor": retest.retest_actor,
        "procedure_description": retest.procedure_description,
        "retest_result": retest.retest_result,
        "effectiveness_conclusion": retest.effectiveness_conclusion,
        "evidence_record_id": retest.evidence_record_id,
        "tested_at": retest.tested_at,
    }


def serialize_closure(closure: FindingClosure) -> dict[str, Any]:
    """Serialize the immutable closure or placeholder risk-acceptance decision."""
    return {
        "finding_closure_id": closure.finding_closure_id,
        "closure_basis": closure.closure_basis,
        "finding_retest_id": closure.finding_retest_id,
        "closing_actor": closure.closing_actor,
        "acceptance_authority_actor": closure.acceptance_authority_actor,
        "acceptance_expires_on": closure.acceptance_expires_on,
        "closure_rationale": closure.closure_rationale,
        "closed_at": closure.closed_at,
    }


def engagement_view(session: Session, engagement_id: str) -> dict[str, Any]:
    """Return the full engagement record: criteria, team, independence, work, findings."""
    engagement = _get_or_404(session, AuditEngagement, engagement_id, "audit engagement")
    criteria = (
        session.query(EngagementCriterion)
        .filter_by(audit_engagement_id=engagement_id)
        .order_by(EngagementCriterion.engagement_criterion_id)
        .all()
    )
    declarations = (
        session.query(IndependenceDeclaration)
        .filter_by(audit_engagement_id=engagement_id)
        .order_by(IndependenceDeclaration.auditor_actor, IndependenceDeclaration.declaration_number)
        .all()
    )
    procedures = (
        session.query(AuditProcedure)
        .filter_by(audit_engagement_id=engagement_id)
        .order_by(AuditProcedure.created_at, AuditProcedure.audit_procedure_id)
        .all()
    )
    findings = (
        session.query(AuditFinding)
        .filter_by(audit_engagement_id=engagement_id)
        .order_by(AuditFinding.created_at, AuditFinding.audit_finding_id)
        .all()
    )
    payload = serialize_engagement(engagement)
    payload.update(
        {
            "criteria": [serialize_criterion(session, criterion) for criterion in criteria],
            "team_members": [
                serialize_team_member(member) for member in _members(session, engagement_id)
            ],
            "independence_declarations": [serialize_declaration(item) for item in declarations],
            "procedures": [
                serialize_procedure(
                    procedure,
                    _sample_ordinals(session, procedure.audit_procedure_id),
                    _procedure_links(session, procedure.audit_procedure_id),
                )
                for procedure in procedures
            ],
            "findings": [serialize_finding_summary(finding) for finding in findings],
        }
    )
    return payload


def finding_view(session: Session, finding_id: str) -> dict[str, Any]:
    """Return a finding with full revision history, remediation, retests, and closure."""
    finding = _get_or_404(session, AuditFinding, finding_id, "audit finding")
    revisions = (
        session.query(AuditFindingRevision)
        .filter_by(audit_finding_id=finding_id)
        .order_by(AuditFindingRevision.revision_number)
        .all()
    )
    retests = (
        session.query(FindingRetest)
        .filter_by(audit_finding_id=finding_id)
        .order_by(FindingRetest.retest_number)
        .all()
    )
    closure = session.query(FindingClosure).filter_by(audit_finding_id=finding_id).one_or_none()
    criterion = _get_referenced(
        session, EngagementCriterion, revisions[-1].engagement_criterion_id
    )
    official = serialize_criterion(session, criterion)
    payload = serialize_finding_summary(finding)
    payload.update(
        {
            "criterion": {
                "framework": official["framework"],
                "catalog_identifier": official["catalog_identifier"],
            },
            "revisions": [serialize_revision(revision) for revision in revisions],
            "remediation_actions": [
                serialize_action(action) for action in _actions(session, finding_id)
            ],
            "retests": [serialize_retest(retest) for retest in retests],
            "closure": None if closure is None else serialize_closure(closure),
        }
    )
    return payload


def serialize_overdue(session: Session, overdue: OverdueRemediation) -> dict[str, Any]:
    """Serialize the overdue remediation view with each action's finding status."""
    actions = []
    for action in overdue.overdue_actions:
        finding = _get_referenced(session, AuditFinding, action.audit_finding_id)
        actions.append(serialize_action(action, finding.finding_status))
    return {
        "as_of": overdue.as_of,
        "overdue_actions": actions,
        "overdue_findings": [serialize_finding_summary(f) for f in overdue.overdue_findings],
    }
