"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import PurposeCode, require_purpose, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.health import health_payload
from cwl_grc.keyverse_authentication import KeyverseAccessTokenVerifier
from cwl_grc.keyverse_http import (
    EVIDENCE_WRITE_SCOPES,
    POLICY_READ_SCOPES,
    POLICY_WRITE_SCOPES,
    authenticate_keyverse_request,
)
from cwl_grc.models import ControlItem, EvidenceRecord, PolicyDocument
from cwl_grc.officer_console import parse_control_ref, render_officer_home
from cwl_grc.policy import (
    ControlRef,
    PolicyGap,
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
    access_token_verifier: KeyverseAccessTokenVerifier | None = None,
) -> FastAPI:
    """Build a local-only GRC app with durable-key enforcement."""
    url = database_url or os.environ.get(
        "CWL_GRC_DATABASE_URL",
        "sqlite:///grc_product.sqlite",
    )
    key = evidence_key if evidence_key is not None else os.environ.get(
        "CWL_GRC_EVIDENCE_KEY"
    )
    factory = create_session_factory(url)
    cipher = EvidenceCipher(
        key,
        allow_ephemeral=url in {"sqlite://", "sqlite:///:memory:"},
    )
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()

    def get_session() -> Iterator[Session]:
        """Yield the request session."""
        yield from session_dependency(factory)

    app = FastAPI(title="CWL GRC", version="0.1.0")
    app.state.evidence_cipher = cipher
    app.state.access_token_verifier = access_token_verifier

    def authorized_actor(
        *,
        authorization: str | None,
        declared_actor: str | None,
        declared_tenant: str | None = None,
        required_scopes: tuple[str, ...] = (),
    ) -> str:
        """Resolve the actor from Keyverse when configured, else the local declaration."""
        return authenticate_keyverse_request(
            access_token_verifier,
            authorization=authorization,
            declared_actor=declared_actor,
            declared_tenant=declared_tenant,
            required_scopes=required_scopes,
        )

    def officer_owned_gaps(
        session: Session,
        actor: str,
        policy_document_id: str | None = None,
    ) -> list[PolicyGap]:
        """Return policy gaps owned by the verified officer only."""
        gaps = list_policy_gaps(session, policy_document_id)
        owned = {
            document.policy_document_id
            for document in session.query(PolicyDocument)
            .filter_by(created_by_actor=actor)
            .all()
        }
        return [gap for gap in gaps if gap.policy_document_id in owned]

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
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Author a policy mapped only to official catalog identifiers."""
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=x_actor_id,
            declared_tenant=x_tenant_id,
            required_scopes=POLICY_WRITE_SCOPES,
        )
        decision = require_purpose(actor, x_purpose, PurposeCode.POLICY_AUTHORING)
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
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Publish the next immutable policy edition and replacement mappings."""
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=x_actor_id,
            declared_tenant=x_tenant_id,
            required_scopes=POLICY_WRITE_SCOPES,
        )
        decision = require_purpose(actor, x_purpose, PurposeCode.POLICY_AUTHORING)
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
        x_actor_id: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List authored policies and their latest official mappings."""
        documents = list_policy_documents(session)
        if access_token_verifier is not None:
            actor = authorized_actor(
                authorization=authorization,
                declared_actor=x_actor_id,
                declared_tenant=x_tenant_id,
                required_scopes=POLICY_READ_SCOPES,
            )
            documents = [
                document
                for document in documents
                if document.created_by_actor == actor
            ]
        return {
            "next_action": "Review policy gaps and attach the next evidence.",
            "policies": [
                serialize_policy(session, document)
                for document in documents
            ],
        }

    @app.get("/policy-gaps")
    def get_policy_gaps(
        session: Session = Depends(get_session),
        policy_document_id: str | None = None,
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List latest-version policy mappings that still lack evidence."""
        if access_token_verifier is not None:
            actor = authorized_actor(
                authorization=authorization,
                declared_actor=x_actor_id,
                declared_tenant=x_tenant_id,
                required_scopes=POLICY_READ_SCOPES,
            )
            gaps = officer_owned_gaps(session, actor, policy_document_id)
        else:
            gaps = list_policy_gaps(session, policy_document_id)
        return {
            "next_action": "Attach the next evidence on an uncovered policy control.",
            "gaps": [serialize_gap(gap) for gap in gaps],
        }

    @app.post("/evidence-records", status_code=201)
    def post_evidence(
        body: dict[str, str],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store the next evidence artifact without masking PII."""
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=x_actor_id,
            declared_tenant=x_tenant_id,
            required_scopes=EVIDENCE_WRITE_SCOPES,
        )
        decision = require_purpose(actor, x_purpose, PurposeCode.EVIDENCE_BINDING)
        record = create_evidence_record(
            session,
            cipher,
            decision,
            body.get("evidence_title", ""),
            body.get("payload_text", ""),
        )
        return _serialize_evidence(record, cipher)

    @app.post("/control-evidence-bindings", status_code=201)
    def post_binding(
        body: dict[str, str],
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Bind stored evidence to one official control identifier."""
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=x_actor_id,
            declared_tenant=x_tenant_id,
            required_scopes=EVIDENCE_WRITE_SCOPES,
        )
        decision = require_purpose(actor, x_purpose, PurposeCode.EVIDENCE_BINDING)
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
    def officer_home(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> str:
        """Show policy authoring, policy gaps, and the next evidence action."""
        if access_token_verifier is not None:
            actor = authorized_actor(
                authorization=authorization,
                declared_actor=x_actor_id,
                declared_tenant=x_tenant_id,
                required_scopes=POLICY_READ_SCOPES,
            )
            gaps = officer_owned_gaps(session, actor)
        else:
            gaps = list_policy_gaps(session, None)
        return render_officer_home(
            list_uncovered_controls(session, None),
            policy_gaps=gaps,
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
        x_tenant_id: str | None = Header(default=None),
    ) -> RedirectResponse:
        """Author a policy from the officer home and return to the gap list."""
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=actor_identifier,
            declared_tenant=x_tenant_id,
            required_scopes=POLICY_WRITE_SCOPES,
        )
        decision = require_purpose(
            actor,
            PurposeCode.POLICY_AUTHORING.value,
            PurposeCode.POLICY_AUTHORING,
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
        x_tenant_id: str | None = Header(default=None),
    ) -> RedirectResponse:
        """Attach evidence from the officer home and return to the gap list."""
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
        actor = authorized_actor(
            authorization=authorization,
            declared_actor=actor_identifier,
            declared_tenant=x_tenant_id,
            required_scopes=EVIDENCE_WRITE_SCOPES,
        )
        decision = require_purpose(
            actor,
            PurposeCode.EVIDENCE_BINDING.value,
            PurposeCode.EVIDENCE_BINDING,
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
    return {
        "evidence_record_id": record.evidence_record_id,
        "evidence_title": record.evidence_title,
        "collector_actor": record.collector_actor,
        "payload_text": cipher.decrypt(record.ciphertext_payload),
        "next_action": "Bind this evidence to the uncovered control.",
    }
