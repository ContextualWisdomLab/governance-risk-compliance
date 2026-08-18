"""FastAPI application factory for standalone and modular GRC use."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from cwl_grc.authorization import PurposeCode, require_purpose, seed_authorization_purposes
from cwl_grc.catalog import FrameworkCode, list_control_items, seed_control_catalog
from cwl_grc.coverage import list_uncovered_controls
from cwl_grc.database import create_session_factory, session_dependency
from cwl_grc.encryption import EvidenceCipher
from cwl_grc.evidence import bind_control_evidence, create_evidence_record
from cwl_grc.health import health_payload
from cwl_grc.models import ControlItem, EvidenceRecord
from cwl_grc.officer_console import parse_control_ref, render_officer_home


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
    """Build the GRC app for module import or a standalone process."""
    url = database_url or os.environ.get("CWL_GRC_DATABASE_URL", "sqlite:///grc_product.sqlite")
    key = evidence_key if evidence_key is not None else os.environ.get("CWL_GRC_EVIDENCE_KEY")
    factory = create_session_factory(url)
    cipher = EvidenceCipher(key)
    with factory() as session:
        seed_control_catalog(session)
        seed_authorization_purposes(session)
        session.commit()

    def get_session() -> Iterator[Session]:
        """Yield the request session."""
        yield from session_dependency(factory)

    app = FastAPI(title="CWL GRC", version="0.1.0")
    app.state.evidence_cipher = cipher

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
            "next_action": "Review remaining uncovered controls and attach the next evidence.",
        }

    @app.get("/", response_class=HTMLResponse)
    def officer_home(session: Session = Depends(get_session)) -> str:
        """Show CSAP / SOC 2 / ISMS-P gaps and the next evidence action."""
        return render_officer_home(list_uncovered_controls(session, None))

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
                raise HTTPException(status_code=400, detail="Choose an uncovered control.") from exc
        parsed = parse_framework(framework)
        if parsed is None or not catalog_identifier:
            raise HTTPException(status_code=400, detail="Name the official control to bind.")
        decision = require_purpose(actor_identifier, PurposeCode.EVIDENCE_BINDING.value, PurposeCode.EVIDENCE_BINDING)
        record = create_evidence_record(session, cipher, decision, evidence_title, payload_text)
        bind_control_evidence(session, decision, parsed, catalog_identifier, record.evidence_record_id)
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
