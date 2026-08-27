"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cwl_grc.authorization import (
    AuthorizationDecision,
    PurposeCode,
    require_purpose,
    seed_authorization_purposes,
)
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.health import health_payload
from cwl_grc.models import ControlItem, EvidenceRecord, IdempotencyRecord, PolicyDocument
from cwl_grc.officer_console import parse_control_ref, render_officer_home
from cwl_grc.policy import (
    ControlRef,
    author_policy,
    list_policy_documents_page,
    list_policy_gaps_page,
    list_policy_documents,
    list_policy_gaps,
    parse_control_refs,
    revise_policy,
    serialize_gap,
    serialize_policy,
    serialize_policy_page,
)
from cwl_grc.remote_access import request_is_local


class V1ControlRefBody(BaseModel):
    """Strict version-one representation of an official control reference."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    framework: FrameworkCode
    catalog_identifier: StrictStr = Field(min_length=1, max_length=64)


class V1PolicyAuthorBody(BaseModel):
    """Strict version-one policy authoring request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    policy_title: StrictStr = Field(min_length=1, max_length=255)
    policy_body: StrictStr = Field(min_length=1, max_length=100_000)
    control_refs: list[V1ControlRefBody] = Field(default_factory=list, max_length=100)


class V1PolicyRevisionBody(BaseModel):
    """Strict version-one policy revision request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    policy_body: StrictStr = Field(min_length=1, max_length=100_000)
    control_refs: list[V1ControlRefBody] = Field(default_factory=list, max_length=100)


def _is_v1_request(request: Request) -> bool:
    """Identify requests covered by the version-one problem contract."""
    return request.url.path.startswith("/v1/")


def _problem_response(
    request: Request,
    status_code: int,
    detail: str,
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457-style response without reflecting request payloads."""
    request_reference = uuid4().hex
    problem_code = code or HTTPStatus(status_code).name.lower()
    content = {
        "type": f"https://grc.contextualwisdomlab.org/problems/{problem_code}",
        "title": HTTPStatus(status_code).phrase,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "request_reference": request_reference,
    }
    response_headers = {"X-Request-ID": request_reference}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=response_headers,
        media_type="application/problem+json",
    )


def _policy_etag(payload: dict[str, Any]) -> str:
    """Return a strong ETag for the persisted current policy representation."""
    material = json.dumps(payload["current_version"], sort_keys=True, separators=(",", ":"))
    return f'"{hashlib.sha256(material.encode()).hexdigest()}"'


def _policy_refs(body: V1PolicyAuthorBody | V1PolicyRevisionBody) -> list[ControlRef]:
    """Convert strict API control references to the policy domain type."""
    return [ControlRef(ref.framework, ref.catalog_identifier) for ref in body.control_refs]


def _request_digest(body: BaseModel) -> str:
    """Hash the validated request body used by an idempotency record."""
    material = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _policy_version_operation(policy_document_id: str) -> str:
    """Scope version idempotency to the target policy without leaking path length."""
    target_digest = hashlib.sha256(policy_document_id.encode()).hexdigest()[:32]
    return f"v1_policy_version_create:{target_digest}"


def _replay_idempotent_record(record: IdempotencyRecord) -> JSONResponse:
    """Return the durable response recorded for an idempotent mutation."""
    payload = json.loads(record.response_payload)
    headers = {"Idempotency-Replayed": "true", "ETag": _policy_etag(payload)}
    return JSONResponse(
        status_code=record.response_status,
        content=payload,
        headers=headers,
    )


def _begin_idempotent_request(
    session: Session,
    decision: AuthorizationDecision,
    operation_name: str,
    idempotency_key: str | None,
    body: BaseModel,
) -> tuple[IdempotencyRecord | None, JSONResponse | None]:
    """Return a replay response or reserve a new purpose-scoped mutation key."""
    key = idempotency_key.strip() if idempotency_key else ""
    if not key or len(key) > 255:
        raise HTTPException(
            status_code=400,
            detail="Provide an Idempotency-Key of 1 to 255 characters.",
        )
    digest = _request_digest(body)
    existing = (
        session.query(IdempotencyRecord)
        .filter_by(
            actor_identifier=decision.actor_identifier,
            operation_name=operation_name,
            idempotency_key=key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise HTTPException(
                status_code=409,
                detail="Reuse the idempotency key only with the original request.",
            )
        return None, _replay_idempotent_record(existing)
    record = IdempotencyRecord(
        idempotency_record_id=uuid4().hex,
        actor_identifier=decision.actor_identifier,
        operation_name=operation_name,
        idempotency_key=key,
        request_digest=digest,
        response_status=0,
        response_payload="{}",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        existing = (
            session.query(IdempotencyRecord)
            .filter_by(
                actor_identifier=decision.actor_identifier,
                operation_name=operation_name,
                idempotency_key=key,
            )
            .one_or_none()
        )
        if existing is None:
            raise HTTPException(
                status_code=409,
                detail="That idempotency key is already in progress; retry the request.",
            ) from exc
        if existing.request_digest != digest:
            raise HTTPException(
                status_code=409,
                detail="Reuse the idempotency key only with the original request.",
            ) from exc
        if existing.response_status == 0:
            raise HTTPException(
                status_code=409,
                detail="That idempotency key is already in progress; retry the request.",
            ) from exc
        return None, _replay_idempotent_record(existing)
    return record, None


def _require_idempotency_record(record: IdempotencyRecord | None) -> IdempotencyRecord:
    """Fail closed when a mutation has no durable idempotency reservation."""
    if record is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "The write reservation could not be confirmed. "
                "Retry the same request with the same Idempotency-Key."
            ),
        )
    return record


def _finish_idempotent_request(
    session: Session,
    record: IdempotencyRecord,
    status_code: int,
    payload: dict[str, Any],
) -> None:
    """Persist the response needed for a later exact-key replay."""
    record.response_status = status_code
    record.response_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    session.flush()


def _require_if_match(if_match: str | None, current_etag: str) -> None:
    """Require the caller to update the policy observed by its ETag."""
    if not if_match:
        raise HTTPException(
            status_code=428,
            detail="Supply If-Match with the current policy ETag before publishing a revision.",
        )
    if if_match.strip() not in {"*", current_etag}:
        raise HTTPException(
            status_code=412,
            detail="The policy ETag is stale; reload the current edition before revising it.",
        )


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

    app = FastAPI(
        title="CWL GRC",
        version="0.1.0",
        description=(
            "Policy/control truth API. Version one is strict and paginated; "
            "this deployment remains a loopback-only developer preview until "
            "Keyverse identity and tenant authorization are enabled."
        ),
    )
    app.state.evidence_cipher = cipher

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """Render version-one HTTP failures as problem details."""
        if not _is_v1_request(request):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be processed."
        return _problem_response(
            request,
            exc.status_code,
            detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Render safe version-one validation details without echoing input values."""
        if not _is_v1_request(request):
            return JSONResponse(
                status_code=422,
                content={"detail": jsonable_encoder(exc.errors())},
            )
        errors = exc.errors()[:5]
        details = "; ".join(
            f"{'body' if error.get('type') == 'extra_forbidden' else '.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in errors
        )
        return _problem_response(request, 422, details or "The request is invalid.")

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

    @app.post("/policy-documents", status_code=201, deprecated=True)
    def post_policy_document(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Author a policy mapped only to official catalog identifiers."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.POLICY_AUTHORING)
        document = author_policy(
            session,
            decision,
            str(body.get("policy_title", "")),
            str(body.get("policy_body", "")),
            parse_control_refs(body.get("control_refs")),
        )
        return serialize_policy(session, document)

    @app.post("/policy-documents/{policy_document_id}/versions", status_code=201, deprecated=True)
    def post_policy_version(
        policy_document_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Publish the next immutable policy edition and replacement mappings."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.POLICY_AUTHORING)
        document = revise_policy(
            session,
            decision,
            policy_document_id,
            str(body.get("policy_body", "")),
            parse_control_refs(body.get("control_refs")),
        )
        return serialize_policy(session, document)

    @app.get("/policy-documents", deprecated=True)
    def get_policy_documents(session: Session = Depends(get_session)) -> dict[str, Any]:
        """List authored policies and their latest official mappings."""
        return {
            "next_action": "Review policy gaps and attach the next evidence.",
            "policies": [
                serialize_policy(session, document)
                for document in list_policy_documents(session)
            ],
        }

    @app.get("/policy-gaps", deprecated=True)
    def get_policy_gaps(
        session: Session = Depends(get_session),
        policy_document_id: str | None = None,
    ) -> dict[str, Any]:
        """List latest-version policy mappings that still lack evidence."""
        return {
            "next_action": "Attach the next evidence on an uncovered policy control.",
            "gaps": [
                serialize_gap(gap)
                for gap in list_policy_gaps(session, policy_document_id)
            ],
        }

    @app.post("/v1/policy-documents", status_code=201)
    def v1_post_policy_document(
        body: V1PolicyAuthorBody,
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
        idempotency_key: str = Header(),
    ) -> Response:
        """Author a bounded, strict, idempotent version-one policy request."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.POLICY_AUTHORING)
        record, replay = _begin_idempotent_request(
            session,
            decision,
            "v1_policy_document_create",
            idempotency_key,
            body,
        )
        if replay is not None:
            return replay
        document = author_policy(
            session,
            decision,
            body.policy_title,
            body.policy_body,
            _policy_refs(body),
        )
        payload = serialize_policy(session, document)
        etag = _policy_etag(payload)
        record = _require_idempotency_record(record)
        _finish_idempotent_request(session, record, 201, payload)
        return JSONResponse(status_code=201, content=payload, headers={"ETag": etag})

    @app.get("/v1/policy-documents")
    def v1_get_policy_documents(
        session: Session = Depends(get_session),
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> dict[str, Any]:
        """List version-one policies with bounded deterministic pagination."""
        documents, next_cursor = list_policy_documents_page(session, limit, cursor)
        return {
            "items": serialize_policy_page(session, documents),
            "next_cursor": next_cursor,
            "limit": limit,
            "next_action": "Review policy gaps and attach the next evidence.",
        }

    @app.get("/v1/policy-documents/{policy_document_id}")
    def v1_get_policy_document(
        policy_document_id: str,
        session: Session = Depends(get_session),
    ) -> Response:
        """Return one version-one policy and its current strong ETag."""
        document = session.get(PolicyDocument, policy_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="That policy document is not on file.")
        payload = serialize_policy(session, document)
        return JSONResponse(
            status_code=200,
            content=payload,
            headers={"ETag": _policy_etag(payload)},
        )

    @app.post("/v1/policy-documents/{policy_document_id}/versions", status_code=201)
    def v1_post_policy_version(
        policy_document_id: str,
        body: V1PolicyRevisionBody,
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
        idempotency_key: str = Header(),
        if_match: str | None = Header(default=None),
    ) -> Response:
        """Publish one immutable version-one edition with an ETag precondition."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.POLICY_AUTHORING)
        record, replay = _begin_idempotent_request(
            session,
            decision,
            _policy_version_operation(policy_document_id),
            idempotency_key,
            body,
        )
        if replay is not None:
            return replay
        document = session.get(PolicyDocument, policy_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="That policy document is not on file.")
        current_payload = serialize_policy(session, document)
        _require_if_match(if_match, _policy_etag(current_payload))
        revised = revise_policy(
            session,
            decision,
            policy_document_id,
            body.policy_body,
            _policy_refs(body),
        )
        payload = serialize_policy(session, revised)
        etag = _policy_etag(payload)
        record = _require_idempotency_record(record)
        _finish_idempotent_request(session, record, 201, payload)
        return JSONResponse(status_code=201, content=payload, headers={"ETag": etag})

    @app.get("/v1/policy-gaps")
    def v1_get_policy_gaps(
        session: Session = Depends(get_session),
        policy_document_id: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> dict[str, Any]:
        """List uncovered version-one mappings with bounded deterministic pagination."""
        gaps, next_cursor = list_policy_gaps_page(
            session,
            policy_document_id,
            limit,
            cursor,
        )
        return {
            "items": [serialize_gap(gap) for gap in gaps],
            "next_cursor": next_cursor,
            "limit": limit,
            "next_action": "Attach the next evidence on an uncovered policy control.",
        }

    @app.post("/evidence-records", status_code=201)
    def post_evidence(
        body: dict[str, str],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store the next evidence artifact without masking PII."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.EVIDENCE_BINDING)
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
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Bind stored evidence to one official control identifier."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.EVIDENCE_BINDING)
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
        """Show policy authoring, policy gaps, and the next evidence action."""
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
    ) -> RedirectResponse:
        """Author a policy from the officer home and return to the gap list."""
        decision = require_purpose(
            actor_identifier,
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
        decision = require_purpose(
            actor_identifier,
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
