"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Iterator
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import PurposeCode, require_purpose, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.catalog_provenance import (
    DEFAULT_CATALOG_SOURCE_HOSTS,
    publish_catalog_release,
    record_catalog_import,
    register_source_artifact,
    register_source_artifact_version,
    seed_source_license_policies,
)
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.health import health_payload
from cwl_grc.models import (
    CatalogImportReceipt,
    CatalogImportRun,
    CatalogRelease,
    ControlItem,
    EvidenceRecord,
    SourceArtifact,
    SourceArtifactVersion,
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


def parse_framework(value: str | None) -> FrameworkCode | None:
    """Parse an optional official framework key."""
    if value is None or value == "":
        return None
    try:
        return FrameworkCode(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown control framework.") from exc


def parse_optional_date(value: Any, label: str) -> date | None:
    """Parse an optional ISO calendar date for catalog source metadata."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{label} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be an ISO date.") from exc


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
        seed_source_license_policies(session)
        seed_authorization_purposes(session)
        session.commit()

    def get_session() -> Iterator[Session]:
        """Yield the request session."""
        yield from session_dependency(factory)

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

    @app.post("/catalog/source-artifacts", status_code=201)
    def post_source_artifact(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Register an allowlisted catalog source pointer for governed acquisition."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        try:
            artifact = register_source_artifact(
                session,
                decision,
                publisher_name=body.get("publisher_name", ""),
                source_reference=body.get("source_reference", ""),
                source_url=body.get("source_url", ""),
                artifact_content_class=body.get("artifact_content_class", ""),
                license_policy_code=body.get("license_policy_code", ""),
                allowed_source_hosts=DEFAULT_CATALOG_SOURCE_HOSTS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _serialize_source_artifact(artifact)

    @app.post("/catalog/source-artifacts/{source_artifact_id}/versions", status_code=201)
    def post_source_artifact_version(
        source_artifact_id: str,
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Register one exact digest and edition without retaining raw source bytes."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        try:
            version = register_source_artifact_version(
                session,
                decision,
                source_artifact_id,
                edition_label=body.get("edition_label", ""),
                content_digest=body.get("content_digest", ""),
                media_type=body.get("media_type", ""),
                byte_length=body.get("byte_length", 0),
                publication_date=parse_optional_date(body.get("publication_date"), "publication date"),
                effective_date=parse_optional_date(body.get("effective_date"), "effective date"),
                withdrawal_date=parse_optional_date(body.get("withdrawal_date"), "withdrawal date"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _serialize_source_artifact_version(version)

    @app.post("/catalog/import-runs", status_code=201)
    def post_catalog_import(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Record an idempotent parser run and its deterministic import receipt."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        try:
            result = record_catalog_import(
                session,
                decision,
                body.get("source_artifact_version_id", ""),
                parser_version=body.get("parser_version", ""),
                importer_commit=body.get("importer_commit", ""),
                run_status=body.get("run_status", ""),
                requirement_count=body.get("requirement_count", 0),
                changed_requirement_count=body.get("changed_requirement_count", 0),
                warning_count=body.get("warning_count", 0),
                failure_code=body.get("failure_code"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _serialize_import_result(result.run, result.receipt, result.created)

    @app.post("/catalog/releases", status_code=201)
    def post_catalog_release(
        body: dict[str, Any],
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Publish a catalog release only after a successful import receipt."""
        decision = require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        try:
            release = publish_catalog_release(
                session,
                decision,
                body.get("source_artifact_version_id", ""),
                release_key=body.get("release_key", ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _serialize_catalog_release(release)

    @app.get("/catalog/releases")
    def get_catalog_releases(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100_000),
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """List a bounded page of published catalog release identities for review."""
        require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        releases = (
            session.query(CatalogRelease)
            .filter_by(release_status="published")
            .order_by(CatalogRelease.created_at.desc(), CatalogRelease.catalog_release_id.desc())
            .offset(offset)
            .limit(limit + 1)
            .all()
        )
        has_more = len(releases) > limit
        return {
            "next_action": "Review the release change set before using it in compliance decisions.",
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "releases": [_serialize_catalog_release(release) for release in releases[:limit]],
        }

    @app.get("/catalog/releases/{catalog_release_id}")
    def get_catalog_release(
        catalog_release_id: str,
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return one governed release provenance snapshot without source bytes."""
        require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        release = session.get(CatalogRelease, catalog_release_id)
        if release is None:
            raise HTTPException(status_code=404, detail="That catalog release is not on file.")
        return {
            "release": _catalog_release_snapshot(release),
            "next_action": "Review the provenance snapshot before using this release in compliance decisions.",
        }

    @app.get("/catalog/releases/{catalog_release_id}/compare/{other_catalog_release_id}")
    def compare_catalog_releases(
        catalog_release_id: str,
        other_catalog_release_id: str,
        session: Session = Depends(get_session),
        x_actor_id: str | None = Header(default=None),
        x_purpose: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Compare two published release identities without exposing source bytes."""
        require_purpose(x_actor_id, x_purpose, PurposeCode.CATALOG_GOVERNANCE)
        from_release = session.get(CatalogRelease, catalog_release_id)
        if from_release is None:
            raise HTTPException(status_code=404, detail="The first catalog release is not on file.")
        _require_published_catalog_release(from_release, "first")
        to_release = session.get(CatalogRelease, other_catalog_release_id)
        if to_release is None:
            raise HTTPException(status_code=404, detail="The second catalog release is not on file.")
        _require_published_catalog_release(to_release, "second")
        return _serialize_catalog_release_comparison(from_release, to_release)

    @app.post("/policy-documents", status_code=201)
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

    @app.post("/policy-documents/{policy_document_id}/versions", status_code=201)
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

    @app.get("/policy-documents")
    def get_policy_documents(session: Session = Depends(get_session)) -> dict[str, Any]:
        """List authored policies and their latest official mappings."""
        return {
            "next_action": "Review policy gaps and attach the next evidence.",
            "policies": [
                serialize_policy(session, document)
                for document in list_policy_documents(session)
            ],
        }

    @app.get("/policy-gaps")
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


def _serialize_source_artifact(artifact: SourceArtifact) -> dict[str, Any]:
    """Return source metadata without exposing or implying stored source bytes."""
    return {
        "source_artifact_id": artifact.source_artifact_id,
        "publisher_name": artifact.publisher_name,
        "source_reference": artifact.source_reference,
        "source_url": artifact.source_url,
        "source_host": artifact.source_host,
        "artifact_content_class": artifact.artifact_content_class,
        "license_policy_code": artifact.license_policy_code,
        "next_action": "Acquire the allowlisted artifact and register its exact digest.",
    }


def _serialize_source_artifact_version(version: SourceArtifactVersion) -> dict[str, Any]:
    """Return immutable source-version identity and lawful storage boundary."""
    return {
        "source_artifact_version_id": version.source_artifact_version_id,
        "source_artifact_id": version.source_artifact_id,
        "edition_label": version.edition_label,
        "publication_date": version.publication_date.isoformat() if version.publication_date else None,
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
        "withdrawal_date": version.withdrawal_date.isoformat() if version.withdrawal_date else None,
        "content_digest": version.content_digest,
        "media_type": version.media_type,
        "byte_length": version.byte_length,
        "version_status": version.version_status,
        "next_action": "Record the parser receipt before publishing a catalog release.",
    }


def _serialize_import_result(
    run: CatalogImportRun,
    receipt: CatalogImportReceipt,
    created: bool,
) -> dict[str, Any]:
    """Return a deterministic import receipt and whether this request created it."""
    return {
        "catalog_import_run_id": run.catalog_import_run_id,
        "source_artifact_version_id": run.source_artifact_version_id,
        "parser_version": run.parser_version,
        "importer_commit": run.importer_commit,
        "run_status": run.run_status,
        "catalog_import_receipt_id": receipt.catalog_import_receipt_id,
        "requirement_count": receipt.requirement_count,
        "changed_requirement_count": receipt.changed_requirement_count,
        "warning_count": receipt.warning_count,
        "receipt_digest": receipt.receipt_digest,
        "created": created,
        "next_action": "Review the receipt and publish the release when the import is accepted.",
    }


def _serialize_catalog_release(release: CatalogRelease) -> dict[str, Any]:
    """Return a published release identity without copying source content."""
    return {
        "catalog_release_id": release.catalog_release_id,
        "source_artifact_version_id": release.source_artifact_version_id,
        "release_key": release.release_key,
        "release_status": release.release_status,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "next_action": "Review the release change set before using it in compliance decisions.",
    }


def _require_published_catalog_release(release: CatalogRelease, label: str) -> None:
    """Reject comparisons involving a draft or withdrawn catalog release."""
    if release.release_status != "published":
        raise HTTPException(status_code=409, detail=f"The {label} catalog release is not published.")


_CATALOG_RELEASE_COMPARISON_FIELDS = (
    "release_key",
    "release_status",
    "source_artifact_id",
    "publisher_name",
    "source_reference",
    "source_url",
    "artifact_content_class",
    "license_policy_code",
    "source_text_storage_allowed",
    "source_text_export_allowed",
    "identifier_export_allowed",
    "edition_label",
    "publication_date",
    "effective_date",
    "withdrawal_date",
    "content_digest",
    "media_type",
    "byte_length",
    "version_status",
    "parser_version",
    "importer_commit",
    "requirement_count",
    "changed_requirement_count",
    "warning_count",
    "receipt_digest",
)


def _serialize_catalog_release_comparison(
    from_release: CatalogRelease,
    to_release: CatalogRelease,
) -> dict[str, Any]:
    """Return a metadata-only change set for two published catalog releases."""
    from_snapshot = _catalog_release_snapshot(from_release)
    to_snapshot = _catalog_release_snapshot(to_release)
    changed_fields = [
        field
        for field in _CATALOG_RELEASE_COMPARISON_FIELDS
        if from_snapshot[field] != to_snapshot[field]
    ]
    unchanged_fields = [
        field
        for field in _CATALOG_RELEASE_COMPARISON_FIELDS
        if from_snapshot[field] == to_snapshot[field]
    ]
    return {
        "from_release": from_snapshot,
        "to_release": to_snapshot,
        "comparison_scope": "source_metadata_and_import_receipt",
        "changed_fields": changed_fields,
        "unchanged_fields": unchanged_fields,
        "limitations": [
            "Requirement-level control-item diff is unavailable until a verified importer publishes official catalog rows."
        ],
        "next_action": "Review the changed provenance fields before using the target release in compliance decisions.",
    }


def _catalog_release_snapshot(release: CatalogRelease) -> dict[str, Any]:
    """Build a release snapshot from immutable source and successful receipt metadata."""
    version = release.source_artifact_version
    artifact = version.source_artifact
    receipt_run = release.catalog_import_run
    if receipt_run is None or receipt_run.run_status != "succeeded" or receipt_run.receipt is None:
        raise HTTPException(
            status_code=409,
            detail="The catalog release has no immutable successful import receipt.",
        )
    if receipt_run.source_artifact_version_id != version.source_artifact_version_id:
        raise HTTPException(
            status_code=409,
            detail="The catalog release import receipt references a different source version.",
        )
    receipt = receipt_run.receipt
    return {
        "catalog_release_id": release.catalog_release_id,
        "release_key": release.release_key,
        "release_status": release.release_status,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "source_artifact_id": artifact.source_artifact_id,
        "publisher_name": artifact.publisher_name,
        "source_reference": artifact.source_reference,
        "source_url": artifact.source_url,
        "artifact_content_class": artifact.artifact_content_class,
        "license_policy_code": artifact.license_policy_code,
        "source_text_storage_allowed": artifact.license_policy.source_text_storage_allowed,
        "source_text_export_allowed": artifact.license_policy.source_text_export_allowed,
        "identifier_export_allowed": artifact.license_policy.identifier_export_allowed,
        "source_artifact_version_id": version.source_artifact_version_id,
        "edition_label": version.edition_label,
        "publication_date": version.publication_date.isoformat() if version.publication_date else None,
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
        "withdrawal_date": version.withdrawal_date.isoformat() if version.withdrawal_date else None,
        "content_digest": version.content_digest,
        "media_type": version.media_type,
        "byte_length": version.byte_length,
        "version_status": version.version_status,
        "parser_version": receipt_run.parser_version,
        "importer_commit": receipt_run.importer_commit,
        "requirement_count": receipt.requirement_count,
        "changed_requirement_count": receipt.changed_requirement_count,
        "warning_count": receipt.warning_count,
        "receipt_digest": receipt.receipt_digest,
    }
