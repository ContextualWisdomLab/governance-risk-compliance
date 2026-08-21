"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
import time
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import (
    AuthorizationDecision,
    LOCAL_DEVELOPMENT_TENANT,
    PurposeCode,
    require_purpose,
    seed_authorization_purposes,
)
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_control_coverage
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher, EvidenceKeyring, make_evidence_context
from cwl_grc.evidence import (
    bind_control_evidence,
    create_evidence_record,
    place_evidence_legal_hold,
    record_encryption_envelope,
    release_evidence_legal_hold,
)
from cwl_grc.evidence_requests import (
    create_evidence_request,
    list_evidence_requests,
    next_action_for_evidence_request,
    review_evidence_request,
    submit_evidence_request,
)
from cwl_grc.health import (
    LOCAL_PREVIEW_ENVIRONMENT,
    LifecycleState,
    ensure_startup_ready,
    health_payload,
    readiness_payload,
)
from cwl_grc.internal_controls import ControlCoverageStatus, next_action_for_coverage
from cwl_grc.keyverse_authentication import (
    AccessTokenValidationError,
    KeyverseAccessTokenVerifier,
    require_access_scopes,
)
from cwl_grc.models import (
    AuditEvent,
    ComplianceObligation,
    ControlItem,
    EvidenceRecord,
    RiskRegister,
)
from cwl_grc.obligations import (
    ApplicabilityCode,
    ObligationWorkItem,
    assess_change_impact,
    create_compliance_obligation,
    create_regulatory_source,
    create_source_revision,
    decide_applicability,
    link_obligation_requirement,
    list_obligation_worklist,
    record_regulatory_change,
)
from cwl_grc.observability import (
    build_request_context,
    emit_request_log,
    reset_verified_principal,
    reset_request_state,
    route_template,
    set_verified_principal,
    set_request_state,
)
from cwl_grc.officer_console import parse_control_ref, render_officer_home
from cwl_grc.policy import (
    ControlRef,
    author_policy,
    list_policy_documents,
    list_policy_gaps,
    parse_control_refs,
    revise_policy,
    serialize_gap,
    serialize_policy,
)
from cwl_grc.remote_access import request_is_local
from cwl_grc.risks import (
    assess_risk,
    create_risk_acceptance,
    create_risk_closure,
    create_risk_methodology,
    create_risk_register,
    create_risk_treatment,
    latest_risk_acceptance,
    latest_risk_assessment,
    latest_risk_closure,
    latest_risk_treatment,
    list_risk_register,
    next_action_for_risk,
    summarize_risk_portfolio,
)
from cwl_grc.telemetry import RequestTelemetry, span_traceparent


MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def parse_framework(value: str | None) -> FrameworkCode | None:
    """Parse an optional official framework key."""
    if value is None or value == "":
        return None
    try:
        return FrameworkCode(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown control framework.") from exc


def parse_optional_timestamp(value: Any, field_name: str = "disposition date") -> datetime | None:
    """Parse one optional ISO-8601 timestamp supplied by an officer workflow."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"The {field_name} must be text.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Use an ISO-8601 {field_name}.") from exc


def parse_required_timestamp(body: dict[str, Any], field_name: str) -> datetime:
    """Parse one required ISO-8601 timestamp from a JSON officer workflow."""
    value = parse_optional_timestamp(body.get(field_name), field_name)
    if value is None:
        raise HTTPException(status_code=400, detail=f"Name the {field_name} timestamp.")
    return value


def serialize_control(
    item: ControlItem,
    *,
    covered: bool | None = None,
    coverage_status: ControlCoverageStatus | str | None = None,
) -> dict[str, Any]:
    """Serialize one official control for officers and consuming services."""
    payload: dict[str, Any] = {
        "framework": item.framework_key,
        "catalog_identifier": item.catalog_identifier,
        "control_title": item.control_title,
        "control_statement": item.control_statement,
    }
    if covered is not None:
        payload["covered"] = covered
    if coverage_status is not None:
        status = coverage_status.value if isinstance(coverage_status, ControlCoverageStatus) else str(coverage_status)
        payload["coverage_status"] = status
        payload["next_action"] = next_action_for_coverage(status)
    return payload


def create_app(
    *,
    database_url: str | None = None,
    evidence_key: str | None = None,
    evidence_keyring: EvidenceKeyring | None = None,
    access_token_verifier: KeyverseAccessTokenVerifier | None = None,
) -> FastAPI:
    """Build a local-only GRC app with optional Keyverse route authentication."""
    url = database_url or os.environ.get(
        "CWL_GRC_DATABASE_URL",
        "sqlite:///grc_product.sqlite",
    )
    environment = os.environ.get("CWL_GRC_ENVIRONMENT", LOCAL_PREVIEW_ENVIRONMENT)
    keyring = evidence_keyring
    key = evidence_key
    if keyring is None and key is None:
        keyring = EvidenceKeyring.from_environment()
    if keyring is None and key is None:
        key = os.environ.get("CWL_GRC_EVIDENCE_KEY")
    cipher = EvidenceCipher(
        key,
        allow_ephemeral=url in {"sqlite://", "sqlite:///:memory:"},
        keyring=keyring,
    )
    telemetry = RequestTelemetry(environment)
    factory = create_session_factory(url, telemetry)
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()
    startup_report = ensure_startup_ready(
        factory,
        cipher,
        environment,
        access_token_verifier,
    )
    def get_session() -> Iterator[Session]:
        """Yield the request session."""
        yield from session_dependency(factory, telemetry)

    def require_request_actor(
        authorization: str | None,
        declared_actor: str | None,
        purpose_value: str | None,
        required_purpose: PurposeCode,
        required_scope: str,
    ):
        """Return a tenant-bound purpose decision from signed identity when enabled."""
        actor_identifier = declared_actor
        tenant_id = LOCAL_DEVELOPMENT_TENANT
        if access_token_verifier is not None:
            if authorization is None:
                raise HTTPException(
                    status_code=401,
                    detail="Present a Keyverse bearer token before this action.",
                )
            scheme, separator, token = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not separator or not token or " " in token:
                raise HTTPException(
                    status_code=401,
                    detail="Present one Keyverse bearer token before this action.",
                )
            try:
                principal = access_token_verifier.verify(token)
            except AccessTokenValidationError as exc:
                raise HTTPException(
                    status_code=401,
                    detail="The Keyverse bearer token is invalid.",
                ) from exc
            try:
                require_access_scopes(principal, {required_scope})
            except AccessTokenValidationError as exc:
                raise HTTPException(
                    status_code=403,
                    detail=f"This action requires the {required_scope} scope.",
                ) from exc
            actor_identifier = principal.actor_id
            tenant_id = principal.tenant_id
            set_verified_principal(principal.tenant_id, principal.actor_id)
        return require_purpose(
            actor_identifier,
            purpose_value,
            required_purpose,
            tenant_id=tenant_id,
        )

    def tenant_for_policy_read(
        authorization: str | None,
        purpose_value: str | None,
    ) -> str:
        """Resolve a tenant for protected policy reads while preserving local mode."""
        if access_token_verifier is None:
            return LOCAL_DEVELOPMENT_TENANT
        return require_request_actor(
            authorization,
            None,
            purpose_value,
            PurposeCode.COVERAGE_REVIEW,
            "grc.policy.read",
        ).tenant_id

    def decision_for_compliance_read(
        authorization: str | None,
        purpose_value: str | None,
    ) -> AuthorizationDecision:
        """Resolve a tenant for obligation reads while preserving local preview mode."""
        if access_token_verifier is None:
            return AuthorizationDecision(
                "compliance-reader",
                PurposeCode.COMPLIANCE_GOVERNANCE,
                LOCAL_DEVELOPMENT_TENANT,
            )
        return require_request_actor(
            authorization,
            None,
            purpose_value,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.read",
        )

    app = FastAPI(title="CWL GRC", version="0.1.0")
    app.state.evidence_cipher = cipher
    app.state.session_factory = factory
    app.state.lifecycle = LifecycleState()
    app.state.lifecycle.mark_ready()
    app.state.startup_report = startup_report
    app.state.telemetry = telemetry
    app.router.add_event_handler("shutdown", app.state.lifecycle.begin_drain)
    app.router.add_event_handler("shutdown", app.state.telemetry.shutdown)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """Return a safe request reference with expected application errors."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_reference": getattr(request.state, "request_reference", None),
            },
            headers={"X-Request-ID": getattr(request.state, "request_reference", "")},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Return validation failures with a safe request reference and no request body."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": error.get("loc"),
                        "msg": error.get("msg"),
                        "type": error.get("type"),
                    }
                    for error in exc.errors()
                ],
                "request_reference": getattr(request.state, "request_reference", None),
            },
            headers={"X-Request-ID": getattr(request.state, "request_reference", "")},
        )

    @app.middleware("http")
    async def enforce_request_boundary_and_observability(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Enforce the local boundary, drain contract, correlation, and safe request logs."""
        context = build_request_context(
            request.headers.get("x-request-id"),
            request.headers.get("traceparent"),
        )
        request.state.request_reference = context.request_id
        request_state_token = set_request_state(request.scope["state"])
        principal_token = set_verified_principal(None, None)
        started_at = time.perf_counter()
        status_code = 500
        error_class: str | None = None
        route = route_template(request.scope)
        with app.state.telemetry.server_span(
            request.method,
            route,
            request.headers,
        ) as span:
            try:
                client_host = getattr(request.client, "host", None)
                local_request = request_is_local(
                    client_host,
                    request.headers.get("x-forwarded-for"),
                    request.headers.get("forwarded"),
                )
                if not local_request:
                    response = JSONResponse(
                        status_code=503,
                        content={
                            "detail": (
                                "Remote preview is disabled. Configure Keyverse-backed identity and "
                                "tenant authorization before exposing CWL GRC."
                            ),
                            "request_reference": context.request_id,
                        },
                    )
                elif request.method in MUTATING_METHODS and app.state.lifecycle.is_draining:
                    response = JSONResponse(
                        status_code=503,
                        content={
                            "detail": "The instance is draining; retry this mutation on a ready instance.",
                            "request_reference": context.request_id,
                        },
                    )
                else:
                    response = await call_next(request)
                status_code = response.status_code
                response.headers["X-Request-ID"] = context.request_id
                response.headers["traceparent"] = span_traceparent(span)
                return response
            except Exception as exc:
                error_class = type(exc).__name__
                raise
            finally:
                route = route_template(request.scope)
                elapsed_seconds = time.perf_counter() - started_at
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                app.state.telemetry.record_request(
                    request.method,
                    route,
                    status_code,
                    elapsed_seconds,
                )
                emit_request_log(
                    context,
                    request.method,
                    route,
                    status_code,
                    elapsed_seconds * 1000,
                    environment,
                    error_class,
                )
                reset_verified_principal(principal_token)
                reset_request_state(request_state_token)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """Return the liveness probe used by orchestrators."""
        return health_payload()

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        """Report dependency readiness with stable reason codes and a truthful status code."""
        report = readiness_payload(
            factory,
            cipher,
            environment,
            access_token_verifier,
            app.state.lifecycle,
        )
        return JSONResponse(
            status_code=200 if report["status"] == "ready" else 503,
            content=report,
        )

    @app.get("/startupz")
    def startupz() -> dict[str, Any]:
        """Report the immutable startup checks that admitted this process."""
        return {
            "status": "started",
            "service": startup_report["service"],
            "environment": startup_report["environment"],
            "checks": startup_report["checks"],
        }

    @app.get("/controls")
    def list_controls(
        session: Session = Depends(get_session),
        framework: str | None = None,
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List official controls and tenant-scoped effectiveness statuses."""
        tenant_id = tenant_for_policy_read(authorization, x_purpose)
        coverage = list_control_coverage(
            session,
            parse_framework(framework),
            tenant_id=tenant_id,
        )
        return {
            "controls": [
                serialize_control(item.control_item, coverage_status=item.status)
                for item in coverage
            ]
        }

    @app.post("/obligations/sources", status_code=201)
    def post_regulatory_source(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Register one authoritative source pointer without copying source text."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        source = create_regulatory_source(
            session,
            decision,
            body.get("source_code", ""),
            body.get("source_kind", ""),
            body.get("source_title", ""),
            body.get("issuing_authority", ""),
            body.get("official_reference_url", ""),
            body.get("license_classification", ""),
            source_artifact_reference=body.get("source_artifact_reference"),
        )
        return {"regulatory_source_id": source.regulatory_source_id, "source_code": source.source_code}

    @app.post("/obligations/sources/{regulatory_source_id}/revisions", status_code=201)
    def post_source_revision(
        regulatory_source_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Append one immutable source edition with its digest and effective dates."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        revision = create_source_revision(
            session,
            decision,
            regulatory_source_id,
            body.get("revision_number"),
            parse_required_timestamp(body, "publication_date"),
            parse_required_timestamp(body, "effective_from"),
            body.get("content_digest", ""),
            body.get("revision_summary", ""),
            withdrawn_at=parse_optional_timestamp(body.get("withdrawn_at"), "withdrawn_at"),
            immutable_artifact_reference=body.get("immutable_artifact_reference"),
        )
        return {"source_revision_id": revision.source_revision_id, "revision_number": revision.revision_number}

    @app.post("/obligations", status_code=201)
    def post_obligation(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Register one source-backed obligation for a precise scope and period."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        obligation = create_compliance_obligation(
            session,
            decision,
            body.get("source_revision_id", ""),
            body.get("obligation_code", ""),
            body.get("obligation_title", ""),
            body.get("obligation_description", ""),
            body.get("obligation_type", ""),
            body.get("scope_type", ""),
            body.get("scope_reference", ""),
            parse_required_timestamp(body, "effective_from"),
            effective_to=parse_optional_timestamp(body.get("effective_to"), "effective_to"),
            jurisdiction_id=body.get("jurisdiction_id"),
        )
        return _serialize_obligation(
            obligation,
            ApplicabilityCode.UNKNOWN.value,
            None,
            "none",
            "Decide applicability for the exact tenant scope.",
        )

    @app.get("/obligations")
    def get_obligations(
        session: Session = Depends(get_session),
        as_of: str | None = None,
        upcoming_days: int = 30,
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List same-tenant obligation status and overdue/upcoming next actions."""
        decision = decision_for_compliance_read(authorization, x_purpose)
        items = list_obligation_worklist(
            session,
            decision,
            as_of=parse_optional_timestamp(as_of, "as_of"),
            upcoming_days=upcoming_days,
        )
        return {"obligations": [_serialize_obligation_item(item) for item in items]}

    @app.get("/compliance-workspace")
    def get_compliance_workspace(
        session: Session = Depends(get_session),
        upcoming_days: int = 30,
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return one tenant-scoped posture read model for the current first slice."""
        decision = decision_for_compliance_read(authorization, x_purpose)
        coverage = list_control_coverage(session, None, tenant_id=decision.tenant_id)
        obligations = list_obligation_worklist(
            session,
            decision,
            upcoming_days=upcoming_days,
        )
        policy_gaps = list_policy_gaps(session, None, tenant_id=decision.tenant_id)
        evidence_requests = list_evidence_requests(session, decision)
        risks = list_risk_register(session, decision)
        unresolved = {
            ControlCoverageStatus.UNKNOWN,
            ControlCoverageStatus.UNASSESSED,
            ControlCoverageStatus.IMPLEMENTED_NOT_TESTED,
            ControlCoverageStatus.DESIGN_EFFECTIVE,
            ControlCoverageStatus.INEFFECTIVE,
            ControlCoverageStatus.EXCEPTION,
            ControlCoverageStatus.STALE,
        }
        coverage_status_counts = {
            status.value: sum(item.status is status for item in coverage)
            for status in ControlCoverageStatus
        }
        applicability_counts = {
            code.value: sum(item.applicability_code == code.value for item in obligations)
            for code in ApplicabilityCode
        }
        review_queue_counts = {
            queue: sum(item.queue == queue for item in obligations)
            for queue in ("overdue", "upcoming", "none")
        }
        evidence_request_state_counts = {
            state: sum(item.request_state == state for item in evidence_requests)
            for state in ("requested", "submitted", "accepted", "rejected")
        }
        risk_assessments = {
            risk.risk_id: latest_risk_assessment(session, decision, risk.risk_id)
            for risk in risks
        }
        risk_treatments = {
            risk.risk_id: latest_risk_treatment(session, decision, risk.risk_id)
            for risk in risks
        }
        risk_acceptances = {
            risk.risk_id: (
                latest_risk_acceptance(
                    session,
                    decision,
                    risk.risk_id,
                    risk_assessment_id=risk_assessments[risk.risk_id].risk_assessment_id,
                )
                if risk_assessments[risk.risk_id] is not None
                else None
            )
            for risk in risks
        }
        risk_closures = {
            risk.risk_id: latest_risk_closure(session, decision, risk.risk_id)
            for risk in risks
        }
        risk_portfolio = summarize_risk_portfolio(
            risks,
            risk_assessments,
            risk_treatments,
            risk_acceptances,
            risk_closures,
        )
        risk_status_counts = {
            status: sum(risk.risk_status == status for risk in risks)
            for status in ("identified", "assessed", "treating", "accepted", "closed")
        }
        risk_actions = [
            {
                "kind": "risk",
                "reference": risk.risk_code,
                "status": (
                    risk_assessments[risk.risk_id].appetite_status
                    if risk_assessments[risk.risk_id] is not None
                    else risk.risk_status
                ),
                "next_action": next_action_for_risk(
                    risk,
                    risk_assessments[risk.risk_id],
                    treatment=risk_treatments[risk.risk_id],
                    acceptance=risk_acceptances[risk.risk_id],
                ),
            }
            for risk in risks
            if risk_assessments[risk.risk_id] is None
            or risk_assessments[risk.risk_id].appetite_status == "above_appetite"
            or (
                risk_treatments[risk.risk_id] is not None
                and risk_treatments[risk.risk_id].plan_status in {"proposed", "approved", "in_progress"}
            )
            or risk_acceptances[risk.risk_id] is not None
            or risk.next_review_at < datetime.now(timezone.utc).replace(tzinfo=None)
        ]
        control_actions = [
            {
                "kind": "control",
                "reference": f"{item.control_item.framework_key}:{item.control_item.catalog_identifier}",
                "status": item.status.value,
                "next_action": next_action_for_coverage(item.status),
            }
            for item in coverage
            if item.status in unresolved
        ]
        obligation_actions = [
            {
                "kind": "obligation",
                "reference": item.obligation.obligation_code,
                "status": item.applicability_code,
                "queue": item.queue,
                "next_action": item.next_action,
            }
            for item in obligations
            if item.applicability_code in {
                ApplicabilityCode.UNKNOWN.value,
                ApplicabilityCode.PENDING_REVIEW.value,
            }
            or item.queue != "none"
        ]
        gap_actions = [
            {
                "kind": "policy_gap",
                "reference": f"{gap.policy_document_id}:{gap.catalog_identifier}",
                "status": gap.coverage_status,
                "next_action": next_action_for_coverage(gap.coverage_status),
            }
            for gap in policy_gaps
        ]
        evidence_request_actions = [
            {
                "kind": "evidence_request",
                "reference": request.evidence_request_id,
                "status": request.request_state,
                "next_action": next_action_for_evidence_request(request.request_state),
            }
            for request in evidence_requests
            if request.request_state != "accepted"
        ]
        return {
            "projection": "controls_obligations_policy_gaps_evidence_requests_risks",
            "posture": {
                "control_total": len(coverage),
                "control_unresolved": sum(item.status in unresolved for item in coverage),
                "coverage_status_counts": coverage_status_counts,
                "obligation_total": len({
                    item.obligation.compliance_obligation_id for item in obligations
                }),
                "obligation_work_item_total": len(obligations),
                "applicability_work_item_counts": applicability_counts,
                "review_queue_work_item_counts": review_queue_counts,
                "policy_gap_total": len(policy_gaps),
                "evidence_request_total": len(evidence_requests),
                "evidence_request_state_counts": evidence_request_state_counts,
                "risk_total": len(risks),
                "risk_status_counts": risk_status_counts,
                "risk_above_appetite_total": sum(
                    assessment is not None and assessment.appetite_status == "above_appetite"
                    for assessment in risk_assessments.values()
                ),
                "risk_portfolio": risk_portfolio,
            },
            "controls": [
                serialize_control(item.control_item, coverage_status=item.status)
                for item in coverage
            ],
            "obligations": [_serialize_obligation_item(item) for item in obligations],
            "policy_gaps": [serialize_gap(gap) for gap in policy_gaps],
            "evidence_requests": [
                _serialize_evidence_request(session, request)
                for request in evidence_requests
            ],
            "risks": [
                _serialize_risk(
                    risk,
                    risk_assessments[risk.risk_id],
                    risk_treatments[risk.risk_id],
                    risk_acceptances[risk.risk_id],
                    risk_closures[risk.risk_id],
                )
                for risk in risks
            ],
            "next_actions": control_actions + obligation_actions + gap_actions + evidence_request_actions + risk_actions,
            "not_yet_projected": [
                "audit_programs",
                "controlled_exports",
            ],
        }

    @app.post("/risk-methodologies", status_code=201)
    def post_risk_methodology(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create one immutable, tenant-scoped risk calculation methodology."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        methodology = create_risk_methodology(
            session,
            decision,
            body.get("methodology_code"),
            body.get("methodology_version"),
            body.get("methodology_title"),
            body.get("likelihood_scale_max"),
            body.get("impact_scale_max"),
            body.get("effective_control_factor_percent"),
            body.get("appetite_threshold"),
            body.get("tolerance_threshold"),
        )
        return _serialize_risk_methodology(methodology)

    @app.post("/risks", status_code=201)
    def post_risk(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create one stable tenant risk identity with a review cadence."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        risk = create_risk_register(
            session,
            decision,
            body.get("risk_code"),
            body.get("risk_title"),
            body.get("risk_scenario"),
            body.get("risk_category"),
            body.get("source_reference"),
            body.get("affected_scope_type"),
            body.get("affected_scope_reference"),
            body.get("owner_reference"),
            body.get("review_cadence_days"),
        )
        return _serialize_risk(risk, None, None, None, None)

    @app.get("/risks")
    def get_risks(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List the tenant risk register with its latest immutable assessment."""
        decision = decision_for_compliance_read(authorization, x_purpose)
        risks = list_risk_register(session, decision)
        risk_assessments = {
            risk.risk_id: latest_risk_assessment(session, decision, risk.risk_id)
            for risk in risks
        }
        return {
            "risks": [
                _serialize_risk(
                    risk,
                    risk_assessments[risk.risk_id],
                    latest_risk_treatment(session, decision, risk.risk_id),
                    (
                        latest_risk_acceptance(
                            session,
                            decision,
                            risk.risk_id,
                            risk_assessment_id=risk_assessments[risk.risk_id].risk_assessment_id,
                        )
                        if risk_assessments[risk.risk_id] is not None
                        else None
                    ),
                    latest_risk_closure(session, decision, risk.risk_id),
                )
                for risk in risks
            ]
        }

    @app.post("/risks/{risk_id}/assessments", status_code=201)
    def post_risk_assessment(
        risk_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Append one versioned inherent/residual risk assessment."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        assessment = assess_risk(
            session,
            decision,
            risk_id,
            body.get("methodology_id"),
            body.get("likelihood"),
            body.get("impact"),
            body.get("assessment_rationale"),
            parse_required_timestamp(body, "next_review_at"),
            body.get("control_links", []),
            expected_revision_number=body.get("expected_revision_number"),
            decision_reference=body.get("decision_reference"),
        )
        return _serialize_risk_assessment(assessment)

    @app.post("/risks/{risk_id}/treatments", status_code=201)
    def post_risk_treatment(
        risk_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create one immutable, versioned treatment plan for an assessed risk."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        plan = create_risk_treatment(
            session,
            decision,
            risk_id,
            body.get("treatment_strategy"),
            body.get("plan_title"),
            body.get("plan_description"),
            body.get("owner_reference"),
            parse_required_timestamp(body, "due_at"),
            expected_revision_number=body.get("expected_revision_number"),
        )
        return _serialize_risk_treatment(plan)

    @app.post("/risks/{risk_id}/acceptances", status_code=201)
    def post_risk_acceptance(
        risk_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create an independent, time-bounded acceptance for an above-appetite risk."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        acceptance = create_risk_acceptance(
            session,
            decision,
            risk_id,
            body.get("risk_assessment_id"),
            body.get("acceptance_reference"),
            body.get("acceptance_rationale"),
            parse_required_timestamp(body, "valid_from"),
            parse_required_timestamp(body, "valid_to"),
            expected_revision_number=body.get("expected_revision_number"),
            escalation_reference=body.get("escalation_reference"),
        )
        return _serialize_risk_acceptance(acceptance)

    @app.post("/risks/{risk_id}/closures", status_code=201)
    def post_risk_closure(
        risk_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Approve immutable risk closure after an independent within-appetite review."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        closure = create_risk_closure(
            session,
            decision,
            risk_id,
            body.get("risk_assessment_id"),
            body.get("closure_reference"),
            body.get("closure_rationale"),
            body.get("closure_evidence_reference"),
            expected_revision_number=body.get("expected_revision_number"),
        )
        return _serialize_risk_closure(closure)

    @app.post("/obligations/{compliance_obligation_id}/applicability-decisions", status_code=201)
    def post_applicability_decision(
        compliance_obligation_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Record an authorized applicability decision with rationale and evidence."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        applicability = decide_applicability(
            session,
            decision,
            compliance_obligation_id,
            body.get("decision_code", ""),
            body.get("scope_type", ""),
            body.get("scope_reference", ""),
            body.get("rationale", ""),
            body.get("evidence_reference", ""),
            parse_required_timestamp(body, "effective_from"),
            parse_required_timestamp(body, "next_review_at"),
            effective_to=parse_optional_timestamp(body.get("effective_to"), "effective_to"),
            applicability_rule_id=body.get("applicability_rule_id"),
            supersedes_decision_id=body.get("supersedes_decision_id"),
        )
        return {
            "applicability_decision_id": applicability.applicability_decision_id,
            "decision_code": applicability.decision_code,
            "next_review_at": applicability.next_review_at.isoformat(),
        }

    @app.post("/obligations/{compliance_obligation_id}/requirements", status_code=201)
    def post_obligation_requirement(
        compliance_obligation_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Propose an obligation link for independent review."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        requirement = link_obligation_requirement(
            session,
            decision,
            compliance_obligation_id,
            body.get("requirement_code", ""),
            body.get("requirement_title", ""),
            body.get("mapping_rationale", ""),
            policy_version_id=body.get("policy_version_id"),
            internal_control_definition_id=body.get("internal_control_definition_id"),
            control_implementation_id=body.get("control_implementation_id"),
            control_item_id=body.get("control_item_id"),
            source_locator=body.get("source_locator"),
        )
        return {"obligation_requirement_id": requirement.obligation_requirement_id, "review_status": requirement.review_status}

    @app.post("/obligations/changes", status_code=201)
    def post_regulatory_change(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Record a source revision change for later impact triage."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        change = record_regulatory_change(
            session,
            decision,
            body.get("source_revision_id", ""),
            body.get("change_code", ""),
            body.get("change_summary", ""),
            body.get("source_diff_reference", ""),
            effective_at=parse_optional_timestamp(body.get("effective_at"), "effective_at"),
        )
        return {"regulatory_change_id": change.regulatory_change_id, "change_status": change.change_status}

    @app.post("/obligations/changes/{regulatory_change_id}/impact-assessments", status_code=201)
    def post_change_impact(
        regulatory_change_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Assign and record one immutable source-change impact assessment."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        assessment = assess_change_impact(
            session,
            decision,
            regulatory_change_id,
            body.get("compliance_obligation_id", ""),
            body.get("impact_status", ""),
            body.get("impact_rationale", ""),
            body.get("assigned_owner_reference", ""),
            body.get("implementation_plan", ""),
            body.get("reapproval_status", ""),
            due_at=parse_optional_timestamp(body.get("due_at"), "due_at"),
        )
        return {
            "change_impact_assessment_id": assessment.change_impact_assessment_id,
            "assessment_number": assessment.assessment_number,
            "reapproval_status": assessment.reapproval_status,
        }

    @app.get("/controls/uncovered")
    def uncovered_controls(
        session: Session = Depends(get_session),
        framework: str | None = None,
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List official controls still needing evidence for the verified tenant."""
        tenant_id = tenant_for_policy_read(authorization, x_purpose)
        coverage = [
            item
            for item in list_control_coverage(
                session,
                parse_framework(framework),
                tenant_id=tenant_id,
            )
            if item.status
            not in {ControlCoverageStatus.OPERATING_EFFECTIVE, ControlCoverageStatus.NOT_APPLICABLE}
        ]
        return {
            "next_action": "Review explicit control statuses and establish the next control test.",
            "controls": [
                serialize_control(item.control_item, coverage_status=item.status)
                for item in coverage
            ],
        }

    @app.post("/policy-documents", status_code=201)
    def post_policy_document(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Author a policy mapped only to official catalog identifiers."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.POLICY_AUTHORING,
            "grc.policy.write",
        )
        document = author_policy(
            session,
            decision,
            str(body.get("policy_title", "")),
            str(body.get("policy_body", "")),
            parse_control_refs(body.get("control_refs")),
        )
        return serialize_policy(session, document)

    @app.post("/policy-documents/{policy_document_id}/versions", status_code=201)
    def post_policy_version(
        policy_document_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Publish the next immutable policy edition and replacement mappings."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.POLICY_AUTHORING,
            "grc.policy.write",
        )
        document = revise_policy(
            session,
            decision,
            policy_document_id,
            str(body.get("policy_body", "")),
            parse_control_refs(body.get("control_refs")),
        )
        return serialize_policy(session, document)

    @app.get("/policy-documents")
    def get_policy_documents(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List only policies visible to the verified tenant."""
        tenant_id = tenant_for_policy_read(authorization, x_purpose)
        return {
            "next_action": "Review explicit control statuses and establish the next control test.",
            "policies": [
                serialize_policy(session, document)
                for document in list_policy_documents(session, tenant_id)
            ],
        }

    @app.get("/policy-gaps")
    def get_policy_gaps(
        session: Session = Depends(get_session),
        policy_document_id: str | None = None,
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List only uncovered policy mappings visible to the verified tenant."""
        tenant_id = tenant_for_policy_read(authorization, x_purpose)
        return {
            "next_action": "Review explicit control statuses and establish the next control test.",
            "gaps": [
                serialize_gap(gap)
                for gap in list_policy_gaps(
                    session,
                    policy_document_id,
                    tenant_id=tenant_id,
                )
            ],
        }

    @app.post("/evidence-records", status_code=201)
    def post_evidence(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store the next evidence artifact without masking PII."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.EVIDENCE_BINDING,
            "grc.evidence.write",
        )
        record = create_evidence_record(
            session,
            cipher,
            decision,
            body.get("evidence_title", ""),
            body.get("payload_text", ""),
            retention_class=body.get("retention_class", "standard"),
            disposition_due_at=parse_optional_timestamp(body.get("disposition_due_at")),
        )
        return _serialize_evidence(record, cipher)

    @app.post("/evidence-records/{evidence_record_id}/legal-hold")
    def post_evidence_legal_hold(
        evidence_record_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Place a verified legal hold without deleting or masking evidence."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.EVIDENCE_RETENTION,
            "grc.evidence.retention",
        )
        record = place_evidence_legal_hold(
            session,
            decision,
            evidence_record_id,
            body.get("hold_reason", ""),
            body.get("hold_authority", ""),
        )
        return _serialize_evidence_retention(record)

    @app.post("/evidence-requests", status_code=201)
    def post_evidence_request(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Create a tenant-scoped request for a named contributor and period."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        request = create_evidence_request(
            session,
            decision,
            body.get("request_title", ""),
            body.get("requested_scope_type", ""),
            body.get("requested_scope_reference", ""),
            parse_required_timestamp(body, "requested_period_from"),
            parse_required_timestamp(body, "requested_period_to"),
            body.get("required_fields"),
            body.get("contributor_reference", ""),
            parse_required_timestamp(body, "due_at"),
            body.get("reuse_policy", ""),
        )
        return _serialize_evidence_request(session, request)

    @app.get("/evidence-requests")
    def get_evidence_requests(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List tenant-scoped request state and audit history without evidence payloads."""
        decision = decision_for_compliance_read(authorization, x_purpose)
        requests = list_evidence_requests(session, decision)
        return {
            "evidence_requests": [
                _serialize_evidence_request(session, request) for request in requests
            ]
        }

    @app.post("/evidence-requests/{evidence_request_id}/submissions")
    def post_evidence_request_submission(
        evidence_request_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Submit an existing same-tenant evidence artifact for one request."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        request = submit_evidence_request(
            session,
            decision,
            evidence_request_id,
            body.get("evidence_record_id", ""),
        )
        return _serialize_evidence_request(session, request)

    @app.post("/evidence-requests/{evidence_request_id}/review")
    def post_evidence_request_review(
        evidence_request_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Accept or reject a contributor submission under a separate actor."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.COMPLIANCE_GOVERNANCE,
            "grc.compliance.write",
        )
        request = review_evidence_request(
            session,
            decision,
            evidence_request_id,
            body.get("decision_code", ""),
            body.get("rejection_reason"),
        )
        return _serialize_evidence_request(session, request)

    @app.post("/evidence-records/{evidence_record_id}/legal-hold/release")
    def post_evidence_legal_hold_release(
        evidence_record_id: str,
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Release a verified legal hold and leave disposition to a later workflow."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.EVIDENCE_RETENTION,
            "grc.evidence.retention",
        )
        record = release_evidence_legal_hold(session, decision, evidence_record_id)
        return _serialize_evidence_retention(record)

    @app.post("/control-evidence-bindings", status_code=201)
    def post_binding(
        body: dict[str, str],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Bind same-tenant stored evidence to one official control identifier."""
        decision = require_request_actor(
            authorization,
            x_actor_id,
            x_purpose,
            PurposeCode.EVIDENCE_BINDING,
            "grc.evidence.write",
        )
        framework = parse_framework(body.get("framework"))
        if framework is None:
            raise HTTPException(status_code=400, detail="Name the official framework.")
        binding = bind_control_evidence(
            session,
            decision,
            framework,
            body.get("catalog_identifier", ""),
            body.get("evidence_record_id", ""),
        )
        return {
            "binding_id": binding.binding_id,
            "control_item_id": binding.control_item_id,
            "evidence_record_id": binding.evidence_record_id,
            "next_action": (
                "Direct evidence binding is compatibility-only and remains unassessed; establish the next control test."
            ),
        }

    @app.get("/", response_class=HTMLResponse)
    def officer_home(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> str:
        """Show tenant policy authoring, policy gaps, and the next evidence action."""
        tenant_id = tenant_for_policy_read(authorization, x_purpose)
        return render_officer_home(
            [
                item
                for item in list_control_coverage(
                    session,
                    None,
                    tenant_id=tenant_id,
                )
                if item.status
                not in {
                    ControlCoverageStatus.OPERATING_EFFECTIVE,
                    ControlCoverageStatus.NOT_APPLICABLE,
                }
            ],
            policy_gaps=list_policy_gaps(session, None, tenant_id=tenant_id),
            catalog_items=list_control_items(session, None),
        )

    @app.post("/officer/policy")
    def officer_author_policy(
        session: Session = Depends(get_session),
        policy_title: str = Form(),
        policy_body: str = Form(),
        actor_identifier: str = Form(),
        control_refs: list[str] = Form(default=[]),
        authorization: str | None = Header(default=None),
    ) -> RedirectResponse:
        """Author a local-development policy from the officer home."""
        decision = require_request_actor(
            authorization,
            actor_identifier,
            PurposeCode.POLICY_AUTHORING.value,
            PurposeCode.POLICY_AUTHORING,
            "grc.policy.write",
        )
        refs: list[ControlRef] = []
        for raw in control_refs:
            try:
                framework_key, catalog_identifier = parse_control_ref(raw)
                framework = FrameworkCode(framework_key)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Choose official controls to map.",
                ) from exc
            refs.append(ControlRef(framework, catalog_identifier))
        author_policy(session, decision, policy_title, policy_body, refs)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/officer/evidence")
    def officer_attach(
        session: Session = Depends(get_session),
        actor_identifier: str = Form(),
        evidence_title: str = Form(),
        payload_text: str = Form(),
        framework: str | None = Form(default=None),
        catalog_identifier: str | None = Form(default=None),
        control_ref: str | None = Form(default=None),
        authorization: str | None = Header(default=None),
    ) -> RedirectResponse:
        """Attach local-development evidence from the officer home."""
        if control_ref:
            try:
                framework, catalog_identifier = parse_control_ref(control_ref)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Choose an uncovered control.",
                ) from exc
        parsed = parse_framework(framework)
        if parsed is None or not catalog_identifier:
            raise HTTPException(
                status_code=400,
                detail="Name the official control to bind.",
            )
        decision = require_request_actor(
            authorization,
            actor_identifier,
            PurposeCode.EVIDENCE_BINDING.value,
            PurposeCode.EVIDENCE_BINDING,
            "grc.evidence.write",
        )
        record = create_evidence_record(
            session,
            cipher,
            decision,
            evidence_title,
            payload_text,
        )
        bind_control_evidence(
            session,
            decision,
            parsed,
            catalog_identifier,
            record.evidence_record_id,
        )
        return RedirectResponse(url="/", status_code=303)

    return app


def _serialize_evidence(record: EvidenceRecord, cipher: EvidenceCipher) -> dict[str, Any]:
    """Return stored evidence with usable, unmasked payload text."""
    payload_text = cipher.decrypt_record(
        record_encryption_envelope(record),
        context=make_evidence_context(record.tenant_id, record.evidence_record_id),
    )
    return {
        "evidence_record_id": record.evidence_record_id,
        "evidence_title": record.evidence_title,
        "collector_actor": record.collector_actor,
        "payload_text": payload_text,
        **_serialize_evidence_retention(record),
        "next_action": "Record a scoped control test before treating this evidence as effective.",
    }


def _serialize_evidence_retention(record: EvidenceRecord) -> dict[str, Any]:
    """Serialize retention state without exposing encryption material."""
    return {
        "retention_class": record.retention_class,
        "retention_started_at": record.retention_started_at.isoformat(),
        "disposition_due_at": (
            record.disposition_due_at.isoformat()
            if record.disposition_due_at is not None
            else None
        ),
        "legal_hold_active": record.legal_hold_active,
        "legal_hold_reason": record.legal_hold_reason,
        "legal_hold_authority": record.legal_hold_authority,
        "disposition_outcome": record.disposition_outcome,
    }


def _serialize_evidence_request(session: Session, request: Any) -> dict[str, Any]:
    """Serialize request workflow metadata, evidence identity, and audit history."""
    audit_history = (
        session.query(AuditEvent)
        .filter_by(
            tenant_id=request.tenant_id,
            resource_kind="evidence_request",
            resource_identifier=request.evidence_request_id,
        )
        .order_by(AuditEvent.recorded_at, AuditEvent.audit_event_id)
        .all()
    )
    return {
        "evidence_request_id": request.evidence_request_id,
        "request_title": request.request_title,
        "requester_actor": request.requester_actor,
        "requested_scope_type": request.requested_scope_type,
        "requested_scope_reference": request.requested_scope_reference,
        "requested_period_from": request.requested_period_from.isoformat(),
        "requested_period_to": request.requested_period_to.isoformat(),
        "required_fields": json.loads(request.required_fields),
        "contributor_reference": request.contributor_reference,
        "due_at": request.due_at.isoformat(),
        "reuse_policy": request.reuse_policy,
        "request_state": request.request_state,
        "evidence_record_id": request.evidence_record_id,
        "submitted_by_actor": request.submitted_by_actor,
        "submitted_at": (
            request.submitted_at.isoformat() if request.submitted_at is not None else None
        ),
        "reviewed_by_actor": request.reviewed_by_actor,
        "reviewed_at": (
            request.reviewed_at.isoformat() if request.reviewed_at is not None else None
        ),
        "rejection_reason": request.rejection_reason,
        "accepted_at": (
            request.accepted_at.isoformat() if request.accepted_at is not None else None
        ),
        "created_at": request.created_at.isoformat(),
        "audit_history": [
            {
                "action_name": event.action_name,
                "actor_identifier": event.actor_identifier,
                "purpose_code": event.purpose_code,
                "recorded_at": event.recorded_at.isoformat(),
            }
            for event in audit_history
        ],
        "next_action": next_action_for_evidence_request(request.request_state),
    }


def _serialize_risk_methodology(methodology: Any) -> dict[str, Any]:
    """Serialize the calculation rule without exposing tenant internals."""
    return {
        "methodology_id": methodology.methodology_id,
        "methodology_code": methodology.methodology_code,
        "methodology_version": methodology.methodology_version,
        "methodology_title": methodology.methodology_title,
        "likelihood_scale_max": methodology.likelihood_scale_max,
        "impact_scale_max": methodology.impact_scale_max,
        "effective_control_factor_percent": methodology.effective_control_factor_percent,
        "control_effectiveness_method": methodology.control_effectiveness_method,
        "appetite_threshold": methodology.appetite_threshold,
        "tolerance_threshold": methodology.tolerance_threshold,
        "aggregation_rule": methodology.aggregation_rule,
        "rounding_policy": methodology.rounding_policy,
    }


def _serialize_risk_assessment(assessment: Any) -> dict[str, Any]:
    """Serialize one immutable risk assessment snapshot."""
    return {
        "risk_assessment_id": assessment.risk_assessment_id,
        "assessment_number": assessment.assessment_number,
        "methodology_id": assessment.methodology_id,
        "likelihood": assessment.likelihood,
        "impact": assessment.impact,
        "inherent_score": assessment.inherent_score,
        "control_effectiveness_factor_percent": assessment.control_effectiveness_factor_percent,
        "residual_score": assessment.residual_score,
        "appetite_status": assessment.appetite_status,
        "aggregation_rule": assessment.aggregation_rule,
        "assessment_rationale": assessment.assessment_rationale,
        "decision_reference": assessment.decision_reference,
        "assessed_by_actor": assessment.assessed_by_actor,
        "assessed_at": assessment.assessed_at.isoformat(),
        "next_review_at": assessment.next_review_at.isoformat(),
    }


def _serialize_risk_treatment(treatment: Any) -> dict[str, Any]:
    """Serialize one immutable treatment-plan version."""
    return {
        "risk_treatment_plan_id": treatment.risk_treatment_plan_id,
        "risk_id": treatment.risk_id,
        "plan_version": treatment.plan_version,
        "treatment_strategy": treatment.treatment_strategy,
        "plan_title": treatment.plan_title,
        "plan_description": treatment.plan_description,
        "owner_reference": treatment.owner_reference,
        "due_at": treatment.due_at.isoformat(),
        "plan_status": treatment.plan_status,
        "created_by_actor": treatment.created_by_actor,
        "created_at": treatment.created_at.isoformat(),
    }


def _serialize_risk_acceptance(acceptance: Any) -> dict[str, Any]:
    """Serialize one immutable, time-bounded risk acceptance."""
    acceptance_status = acceptance.acceptance_status
    if (
        acceptance_status == "active"
        and acceptance.valid_to <= datetime.now(timezone.utc).replace(tzinfo=None)
    ):
        acceptance_status = "expired"
    return {
        "risk_acceptance_id": acceptance.risk_acceptance_id,
        "risk_id": acceptance.risk_id,
        "risk_assessment_id": acceptance.risk_assessment_id,
        "acceptance_reference": acceptance.acceptance_reference,
        "acceptance_rationale": acceptance.acceptance_rationale,
        "escalation_reference": acceptance.escalation_reference,
        "accepted_by_actor": acceptance.accepted_by_actor,
        "accepted_at": acceptance.accepted_at.isoformat(),
        "valid_from": acceptance.valid_from.isoformat(),
        "valid_to": acceptance.valid_to.isoformat(),
        "acceptance_status": acceptance_status,
    }


def _serialize_risk_closure(closure: Any) -> dict[str, Any]:
    """Serialize one immutable independent risk-closure approval."""
    return {
        "risk_closure_id": closure.risk_closure_id,
        "risk_id": closure.risk_id,
        "risk_assessment_id": closure.risk_assessment_id,
        "closure_reference": closure.closure_reference,
        "closure_rationale": closure.closure_rationale,
        "closure_evidence_reference": closure.closure_evidence_reference,
        "closed_by_actor": closure.closed_by_actor,
        "closed_at": closure.closed_at.isoformat(),
    }


def _serialize_risk(
    risk: RiskRegister,
    assessment: Any,
    treatment: Any,
    acceptance: Any,
    closure: Any,
) -> dict[str, Any]:
    """Serialize tenant risk identity and latest immutable assessment."""
    return {
        "risk_id": risk.risk_id,
        "risk_code": risk.risk_code,
        "risk_title": risk.risk_title,
        "risk_scenario": risk.risk_scenario,
        "risk_category": risk.risk_category,
        "source_reference": risk.source_reference,
        "affected_scope_type": risk.affected_scope_type,
        "affected_scope_reference": risk.affected_scope_reference,
        "owner_reference": risk.owner_reference,
        "risk_status": risk.risk_status,
        "revision_number": risk.revision_number,
        "review_cadence_days": risk.review_cadence_days,
        "next_review_at": risk.next_review_at.isoformat(),
        "assessment": _serialize_risk_assessment(assessment) if assessment is not None else None,
        "treatment": _serialize_risk_treatment(treatment) if treatment is not None else None,
        "acceptance": _serialize_risk_acceptance(acceptance) if acceptance is not None else None,
        "closure": _serialize_risk_closure(closure) if closure is not None else None,
        "next_action": next_action_for_risk(
            risk,
            assessment,
            treatment=treatment,
            acceptance=acceptance,
        ),
    }


def _serialize_obligation(
    obligation: ComplianceObligation,
    applicability_code: str,
    next_review_at: datetime | None,
    queue: str,
    next_action: str,
    *,
    scope_type: str | None = None,
    scope_reference: str | None = None,
) -> dict[str, Any]:
    """Serialize obligation truth without copying an external source body."""
    return {
        "compliance_obligation_id": obligation.compliance_obligation_id,
        "obligation_code": obligation.obligation_code,
        "obligation_title": obligation.obligation_title,
        "obligation_type": obligation.obligation_type,
        "scope_type": scope_type or obligation.scope_type,
        "scope_reference": scope_reference or obligation.scope_reference,
        "source_revision_id": obligation.source_revision_id,
        "applicability_code": applicability_code,
        "next_review_at": next_review_at.isoformat() if next_review_at is not None else None,
        "queue": queue,
        "next_action": next_action,
    }


def _serialize_obligation_item(item: ObligationWorkItem) -> dict[str, Any]:
    """Serialize one obligation worklist projection."""
    return _serialize_obligation(
        item.obligation,
        item.applicability_code,
        item.next_review_at,
        item.queue,
        item.next_action,
        scope_type=item.scope_type,
        scope_reference=item.scope_reference,
    )
