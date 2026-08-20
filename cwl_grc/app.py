"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import (
    LOCAL_DEVELOPMENT_TENANT,
    PurposeCode,
    require_purpose,
    seed_authorization_purposes,
)
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher, EvidenceKeyring, make_evidence_context
from cwl_grc.evidence import (
    bind_control_evidence,
    create_evidence_record,
    place_evidence_legal_hold,
    record_encryption_envelope,
    release_evidence_legal_hold,
)
from cwl_grc.health import health_payload
from cwl_grc.keyverse_authentication import (
    AccessTokenValidationError,
    KeyverseAccessTokenVerifier,
    require_access_scopes,
)
from cwl_grc.models import ControlItem, EvidenceRecord
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


def parse_framework(value: str | None) -> FrameworkCode | None:
    """Parse an optional official framework key."""
    if value is None or value == "":
        return None
    try:
        return FrameworkCode(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown control framework.") from exc


def parse_optional_timestamp(value: Any) -> datetime | None:
    """Parse one optional ISO-8601 timestamp supplied by an officer workflow."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="A disposition date must be text.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Use an ISO-8601 disposition date.") from exc


def serialize_control(item: ControlItem, *, covered: bool | None = None) -> dict[str, Any]:
    """Serialize one official control for officers and consuming services."""
    payload: dict[str, Any] = {
        "framework": item.framework_key,
        "catalog_identifier": item.catalog_identifier,
        "control_title": item.control_title,
        "control_statement": item.control_statement,
    }
    if covered is not None:
        payload["covered"] = covered
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
    keyring = evidence_keyring
    key = evidence_key
    if keyring is None and key is None:
        keyring = EvidenceKeyring.from_environment()
    if keyring is None and key is None:
        key = os.environ.get("CWL_GRC_EVIDENCE_KEY")
    factory = create_session_factory(url)
    cipher = EvidenceCipher(
        key,
        allow_ephemeral=url in {"sqlite://", "sqlite:///:memory:"},
        keyring=keyring,
    )
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()

    def get_session() -> Iterator[Session]:
        """Yield the request session."""
        yield from session_dependency(factory)

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

    app = FastAPI(title="CWL GRC", version="0.1.0")
    app.state.evidence_cipher = cipher

    @app.middleware("http")
    async def enforce_developer_preview_boundary(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Reject every non-loopback or proxy-forwarded request until real auth exists."""
        client_host = getattr(request.client, "host", None)
        local_request = request_is_local(
            client_host,
            request.headers.get("x-forwarded-for"),
            request.headers.get("forwarded"),
        )
        if not local_request:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "Remote preview is disabled. Configure Keyverse-backed identity and "
                        "tenant authorization before exposing CWL GRC."
                    )
                },
            )
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """Return the liveness probe used by orchestrators."""
        return health_payload()

    @app.get("/controls")
    def list_controls(
        session: Session = Depends(get_session),
        framework: str | None = None,
    ) -> dict[str, Any]:
        """List official controls, optionally limited to one catalog."""
        items = list_control_items(session, parse_framework(framework))
        return {"controls": [serialize_control(item) for item in items]}

    @app.get("/controls/uncovered")
    def uncovered_controls(
        session: Session = Depends(get_session),
        framework: str | None = None,
    ) -> dict[str, Any]:
        """List official controls that still need evidence."""
        items = list_uncovered_controls(session, parse_framework(framework))
        return {
            "next_action": "Attach the next evidence on an uncovered control.",
            "controls": [serialize_control(item, covered=False) for item in items],
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
            "next_action": "Review policy gaps and attach the next evidence.",
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
            "next_action": "Attach the next evidence on an uncovered policy control.",
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
                "Review remaining uncovered controls and attach the next evidence."
            ),
        }

    @app.get("/", response_class=HTMLResponse)
    def officer_home(session: Session = Depends(get_session)) -> str:
        """Show local policy authoring, policy gaps, and the next evidence action."""
        return render_officer_home(
            list_uncovered_controls(session, None),
            policy_gaps=list_policy_gaps(session, None),
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
        "next_action": "Bind this evidence to the uncovered control.",
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
