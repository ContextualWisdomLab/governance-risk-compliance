"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import (
    AuthorizationDecision,
    LOCAL_DEVELOPMENT_ACTOR,
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
from cwl_grc.models import ComplianceObligation, ControlItem, EvidenceRecord
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
        _declared_actor: str | None,
        purpose_value: str | None,
        required_purpose: PurposeCode,
        required_scope: str,
    ):
        """Return a tenant-bound decision using fixed local or signed identity."""
        actor_identifier = LOCAL_DEVELOPMENT_ACTOR
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

    def tenant_for_coverage_read(
        authorization: str | None,
        purpose_value: str | None,
    ) -> str:
        """Resolve the exact tenant for protected catalog and coverage reads."""
        if access_token_verifier is None:
            return LOCAL_DEVELOPMENT_TENANT
        return require_request_actor(
            authorization,
            None,
            purpose_value,
            PurposeCode.COVERAGE_REVIEW,
            "grc.control.read",
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
        tenant_id = tenant_for_coverage_read(authorization, x_purpose)
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
        tenant_id = tenant_for_coverage_read(authorization, x_purpose)
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
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Author a policy mapped only to official catalog identifiers."""
        decision = require_request_actor(
            authorization,
            None,
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
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Publish the next immutable policy edition and replacement mappings."""
        decision = require_request_actor(
            authorization,
            None,
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
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store the next evidence artifact without masking PII."""
        decision = require_request_actor(
            authorization,
            None,
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
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Place a verified legal hold without deleting or masking evidence."""
        decision = require_request_actor(
            authorization,
            None,
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

    @app.post("/evidence-records/{evidence_record_id}/legal-hold/release")
    def post_evidence_legal_hold_release(
        evidence_record_id: str,
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Release a verified legal hold and leave disposition to a later workflow."""
        decision = require_request_actor(
            authorization,
            None,
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
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Bind same-tenant stored evidence to one official control identifier."""
        decision = require_request_actor(
            authorization,
            None,
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
        control_refs: list[str] = Form(default=[]),
        authorization: str | None = Header(default=None),
    ) -> RedirectResponse:
        """Author a local-development policy from the officer home."""
        decision = require_request_actor(
            authorization,
            None,
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
            None,
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
