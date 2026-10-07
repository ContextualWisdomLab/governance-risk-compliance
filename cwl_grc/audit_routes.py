"""HTTP routes for audit programs, engagements, findings, remediation, and closure.

Every audit-route response, success or rejection, is JSON that states the
officer's ``next_action``. ``X-Actor-Id`` and ``X-Purpose`` remain declarations
for audit context, not authentication; the loopback-only boundary still applies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from cwl_grc import audit_management as service
from cwl_grc.audit_management import AuditWorkflowError
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
from cwl_grc.authorization import AuthorizationDecision, PurposeCode, require_purpose

AUDIT_PATH_PREFIXES = ("/audit-", "/remediation-actions")
"""Path prefixes whose validation errors use the audit next-action contract."""


def audit_decision(
    actor_identifier: str | None,
    purpose_value: str | None,
    required: PurposeCode,
) -> AuthorizationDecision:
    """Apply ``require_purpose`` and restate its rejection with a next action."""
    try:
        return require_purpose(actor_identifier, purpose_value, required)
    except HTTPException as exc:
        if exc.status_code == 401:
            next_action = (
                f"Send X-Actor-Id and X-Purpose: {required.value} headers and retry."
            )
        else:
            next_action = f"Retry with X-Purpose: {required.value}."
        raise AuditWorkflowError(exc.status_code, str(exc.detail), next_action) from exc


def audit_purpose(required: PurposeCode) -> Callable[..., AuthorizationDecision]:
    """Return a dependency that checks the declared purpose before the body is validated.

    FastAPI resolves dependencies before it validates the request body, so a caller
    without ``X-Actor-Id`` / ``X-Purpose`` receives 401/403, not a schema error.
    """

    def declared_purpose(
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> AuthorizationDecision:
        """Accept only a declared actor acting under the required purpose."""
        return audit_decision(x_actor_id, x_purpose, required)

    return declared_purpose


def _with_next_action(payload: dict[str, Any], next_action: str) -> dict[str, Any]:
    """Attach the officer's next action to a success payload."""
    payload["next_action"] = next_action
    return payload


async def audit_workflow_error_handler(request: Request, exc: AuditWorkflowError) -> Response:
    """Return a rejected audit step as ``{"detail", "next_action"}``."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "next_action": exc.next_action},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
    """Add a next action to audit-path validation errors; keep the default elsewhere."""
    if not request.url.path.startswith(AUDIT_PATH_PREFIXES):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "next_action": "Correct the listed fields and send only the documented fields.",
        },
    )


def register_audit_routes(app: FastAPI, get_session: Callable[[], Iterator[Session]]) -> None:
    """Register audit-management routes and their error contract on ``app``."""
    app.add_exception_handler(AuditWorkflowError, audit_workflow_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.post("/audit-programs", status_code=201)
    def post_audit_program(
        body: AuditProgramRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Plan a draft audit program."""
        program = service.create_program(session, decision, body)
        return _with_next_action(
            service.serialize_program(program),
            f"Ask the audit authority {program.audit_authority_actor} to approve the program.",
        )

    @app.post("/audit-programs/{audit_program_id}/approval")
    def post_audit_program_approval(
        audit_program_id: str,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Approve a draft audit program."""
        program = service.approve_program(session, decision, audit_program_id)
        return _with_next_action(
            service.serialize_program(program), "Plan the first engagement under this program."
        )

    @app.post("/audit-programs/{audit_program_id}/engagements", status_code=201)
    def post_audit_engagement(
        audit_program_id: str,
        body: AuditEngagementRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Plan an engagement under an approved program."""
        engagement = service.create_engagement(session, decision, audit_program_id, body)
        return _with_next_action(
            service.serialize_engagement(engagement),
            "Add official criteria and an independent, competent team.",
        )

    @app.get("/audit-engagements/{audit_engagement_id}")
    def get_audit_engagement(
        audit_engagement_id: str,
        session: Session = Depends(get_session),
        _decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Return the full engagement record."""
        return _with_next_action(
            service.engagement_view(session, audit_engagement_id),
            "Review the engagement record and perform the next step for its status.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/criteria", status_code=201)
    def post_engagement_criterion(
        audit_engagement_id: str,
        body: EngagementCriterionRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Add an official catalog control as an audit criterion."""
        criterion = service.add_criterion(session, decision, audit_engagement_id, body)
        return _with_next_action(
            service.serialize_criterion(session, criterion),
            "Add another criterion or assign the engagement team.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/team-members", status_code=201)
    def post_team_member(
        audit_engagement_id: str,
        body: TeamMemberRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Assign one competent auditor to the engagement."""
        member = service.add_team_member(session, decision, audit_engagement_id, body)
        return _with_next_action(
            service.serialize_team_member(member),
            f"Ask {member.auditor_actor} to record an independence declaration.",
        )

    @app.post(
        "/audit-engagements/{audit_engagement_id}/independence-declarations", status_code=201
    )
    def post_independence_declaration(
        audit_engagement_id: str,
        body: IndependenceDeclarationRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Append the requesting auditor's independence declaration."""
        declaration = service.declare_independence(session, decision, audit_engagement_id, body)
        return _with_next_action(
            service.serialize_declaration(declaration),
            "Start fieldwork once every team member is declared independent.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/start")
    def post_engagement_start(
        audit_engagement_id: str,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Move a ready engagement into fieldwork."""
        engagement = service.start_engagement(session, decision, audit_engagement_id)
        return _with_next_action(
            service.serialize_engagement(engagement),
            "Document procedures with reproducible samples and link evidence.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/reporting")
    def post_engagement_reporting(
        audit_engagement_id: str,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Move fieldwork to reporting."""
        engagement = service.move_to_reporting(session, decision, audit_engagement_id)
        return _with_next_action(
            service.serialize_engagement(engagement),
            "Resolve every finding, then close the engagement.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/closure")
    def post_engagement_closure(
        audit_engagement_id: str,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Close a reported engagement with no unresolved findings."""
        engagement = service.close_engagement(session, decision, audit_engagement_id)
        return _with_next_action(
            service.serialize_engagement(engagement),
            "Plan the next engagement in the audit program.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/procedures", status_code=201)
    def post_audit_procedure(
        audit_engagement_id: str,
        body: AuditProcedureRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Document a procedure and return its selected sample ordinals."""
        procedure, ordinals = service.create_procedure(session, decision, audit_engagement_id, body)
        return _with_next_action(
            service.serialize_procedure(procedure, ordinals),
            "Test the selected sample and link the supporting evidence.",
        )

    @app.post("/audit-procedures/{audit_procedure_id}/evidence-links", status_code=201)
    def post_evidence_link(
        audit_procedure_id: str,
        body: EvidenceLinkRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Reference existing evidence from a procedure or one sample item."""
        link = service.link_evidence(session, decision, audit_procedure_id, body)
        return _with_next_action(
            service.serialize_evidence_link(link),
            "Link the next sample's evidence or record any finding.",
        )

    @app.post("/audit-engagements/{audit_engagement_id}/findings", status_code=201)
    def post_audit_finding(
        audit_engagement_id: str,
        body: FindingIssueRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Issue a finding with its first revision."""
        finding = service.issue_finding(session, decision, audit_engagement_id, body)
        return _with_next_action(
            service.serialize_finding_summary(finding),
            f"Ask {finding.remediation_owner_actor} to record remediation actions.",
        )

    @app.post("/audit-findings/{audit_finding_id}/revisions", status_code=201)
    def post_finding_revision(
        audit_finding_id: str,
        body: FindingRevisionRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Append the next finding revision."""
        finding = service.revise_finding(session, decision, audit_finding_id, body)
        return _with_next_action(
            service.serialize_finding_summary(finding),
            "Review the revision history and track remediation.",
        )

    @app.get("/audit-findings/{audit_finding_id}")
    def get_audit_finding(
        audit_finding_id: str,
        session: Session = Depends(get_session),
        _decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Return a finding with its full revision history."""
        return _with_next_action(
            service.finding_view(session, audit_finding_id),
            "Perform the next remediation, retest, or closure step for this finding.",
        )

    @app.post("/audit-findings/{audit_finding_id}/remediation-actions", status_code=201)
    def post_remediation_action(
        audit_finding_id: str,
        body: RemediationActionRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.REMEDIATION_TRACKING)),
    ) -> dict[str, Any]:
        """Record a remediation action by the remediation owner."""
        action = service.create_remediation_action(session, decision, audit_finding_id, body)
        return _with_next_action(
            service.serialize_action(action),
            f"Ask {action.owner_actor} to complete the action with evidence.",
        )

    @app.post("/remediation-actions/{remediation_action_id}/completion")
    def post_action_completion(
        remediation_action_id: str,
        body: ActionCompletionRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.REMEDIATION_TRACKING)),
    ) -> dict[str, Any]:
        """Complete a remediation action with evidence."""
        action = service.complete_remediation_action(session, decision, remediation_action_id, body)
        return _with_next_action(
            service.serialize_action(action),
            "Ask an independent engagement auditor to retest the finding.",
        )

    @app.post("/audit-findings/{audit_finding_id}/retests", status_code=201)
    def post_finding_retest(
        audit_finding_id: str,
        body: FindingRetestRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Record an independent retest."""
        retest, finding = service.record_retest(session, decision, audit_finding_id, body)
        payload = service.serialize_retest(retest)
        payload["finding_status"] = finding.finding_status
        next_action = (
            "Ask the engagement lead or a supervisor to close the finding."
            if retest.retest_result == "passed"
            else "Ask the remediation owner to record further remediation actions."
        )
        return _with_next_action(payload, next_action)

    @app.post("/audit-findings/{audit_finding_id}/closure", status_code=201)
    def post_finding_closure(
        audit_finding_id: str,
        body: FindingClosureRequest,
        session: Session = Depends(get_session),
        decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """Close a finding or record a bounded risk acceptance."""
        closure, finding = service.close_finding(session, decision, audit_finding_id, body)
        payload = service.serialize_closure(closure)
        payload["audit_finding_id"] = finding.audit_finding_id
        payload["finding_status"] = finding.finding_status
        return _with_next_action(
            payload, "Close the engagement once every finding is resolved."
        )

    @app.get("/audit-remediation/overdue")
    def get_overdue_remediation(
        session: Session = Depends(get_session),
        as_of: date | None = None,
        _decision: AuthorizationDecision = Depends(audit_purpose(PurposeCode.AUDIT_ENGAGEMENT)),
    ) -> dict[str, Any]:
        """List overdue remediation actions and findings."""
        overdue = service.list_overdue_remediation(session, as_of)
        return _with_next_action(
            service.serialize_overdue(session, overdue),
            "Follow up with the owners of every overdue action and finding.",
        )
