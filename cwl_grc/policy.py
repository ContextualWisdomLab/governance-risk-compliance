"""Author, version, and gap-query policies that map only official controls."""

from __future__ import annotations

from dataclasses import dataclass
import base64
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session

from cwl_grc.audit import record_audit_event
from cwl_grc.authorization import AuthorizationDecision
from cwl_grc.catalog import FrameworkCode, get_control_item
from cwl_grc.models import (
    ControlEvidenceBinding,
    ControlItem,
    PolicyControlMapping,
    PolicyDocument,
    PolicyVersion,
)


@dataclass(frozen=True)
class ControlRef:
    """One official catalog identifier named by an officer."""

    framework: FrameworkCode
    catalog_identifier: str


@dataclass(frozen=True)
class PolicyGap:
    """A latest-version policy mapping that still lacks evidence."""

    policy_document_id: str
    policy_title: str
    version_number: int
    framework: str
    catalog_identifier: str
    control_title: str


def parse_control_refs(raw_refs: Any) -> list[ControlRef]:
    """Parse officer-supplied mappings; reject unknown frameworks."""
    if raw_refs is None:
        return []
    if not isinstance(raw_refs, list):
        raise HTTPException(status_code=400, detail="Map official controls as a list of catalog refs.")
    refs: list[ControlRef] = []
    for item in raw_refs:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each control ref needs a framework and catalog identifier.")
        try:
            framework = FrameworkCode(item.get("framework"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unknown control framework.") from exc
        identifier = str(item.get("catalog_identifier") or "").strip()
        if not identifier:
            raise HTTPException(status_code=400, detail="Name the official catalog identifier.")
        refs.append(ControlRef(framework, identifier))
    return refs


def parse_cli_control_map(raw: str) -> ControlRef:
    """Parse a CLI ``FRAMEWORK:IDENTIFIER`` mapping."""
    framework_key, separator, catalog_identifier = raw.partition(":")
    if not separator or not framework_key or not catalog_identifier:
        raise HTTPException(status_code=400, detail="Map official controls as FRAMEWORK:IDENTIFIER.")
    try:
        framework = FrameworkCode(framework_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown control framework.") from exc
    return ControlRef(framework, catalog_identifier)


def resolve_control_refs(session: Session, refs: list[ControlRef]) -> list[ControlItem]:
    """Load official controls; never invent a second catalog."""
    items: list[ControlItem] = []
    for ref in refs:
        item = get_control_item(session, ref.framework, ref.catalog_identifier)
        if item is None:
            raise HTTPException(status_code=404, detail="That official control is not in the catalog.")
        items.append(item)
    return items


def author_policy(
    session: Session,
    decision: AuthorizationDecision,
    policy_title: str,
    policy_body: str,
    refs: list[ControlRef],
) -> PolicyDocument:
    """Create a policy document and its first finalized edition."""
    title = policy_title.strip()
    body = policy_body.strip()
    if not title or not body:
        raise HTTPException(status_code=400, detail="A policy needs a title and the next edition text.")
    controls = resolve_control_refs(session, refs)
    document = PolicyDocument(
        policy_document_id=uuid4().hex,
        policy_title=title,
        created_by_actor=decision.actor_identifier,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        current_version_number=1,
    )
    session.add(document)
    session.flush()
    _write_version(session, decision, document, 1, body, controls)
    record_audit_event(
        session,
        decision,
        action_name="author_policy",
        resource_kind="policy_document",
        resource_identifier=document.policy_document_id,
    )
    session.flush()
    return document


def revise_policy(
    session: Session,
    decision: AuthorizationDecision,
    policy_document_id: str,
    policy_body: str,
    refs: list[ControlRef],
) -> PolicyDocument:
    """Atomically allocate and append the next immutable policy edition."""
    document = session.get(PolicyDocument, policy_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="That policy document is not on file.")
    body = policy_body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="A policy revision needs the next edition text.")
    controls = resolve_control_refs(session, refs)
    next_number = _allocate_next_version_number(session, document)
    _write_version(session, decision, document, next_number, body, controls)
    record_audit_event(
        session,
        decision,
        action_name="revise_policy",
        resource_kind="policy_document",
        resource_identifier=document.policy_document_id,
    )
    session.flush()
    return document


def current_version(session: Session, document: PolicyDocument) -> PolicyVersion:
    """Return the latest finalized edition of a policy document."""
    version = (
        session.query(PolicyVersion)
        .filter_by(
            policy_document_id=document.policy_document_id,
            is_finalized=True,
        )
        .order_by(PolicyVersion.version_number.desc())
        .first()
    )
    if version is None:  # pragma: no cover
        raise HTTPException(status_code=404, detail="That policy has no finalized editions.")
    return version


def list_policy_documents(session: Session) -> list[PolicyDocument]:
    """List authored policy documents, newest first."""
    return list(session.query(PolicyDocument).order_by(PolicyDocument.created_at.desc()).all())


def encode_page_cursor(*parts: str) -> str:
    """Encode stable page-sort values as an opaque cursor."""
    payload = json.dumps(list(parts), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_page_cursor(cursor: str, part_count: int) -> tuple[str, ...]:
    """Decode a cursor and reject malformed or incorrectly shaped values."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="The page cursor is invalid.") from exc
    if not isinstance(parts, list) or len(parts) != part_count or not all(
        isinstance(part, str) for part in parts
    ):
        raise HTTPException(status_code=400, detail="The page cursor is invalid.")
    return tuple(parts)


def list_policy_documents_page(
    session: Session,
    limit: int,
    cursor: str | None,
) -> tuple[list[PolicyDocument], str | None]:
    """Return a deterministic keyset page of policy documents."""
    query = session.query(PolicyDocument)
    if cursor:
        created_at_text, policy_document_id = decode_page_cursor(cursor, 2)
        try:
            created_at = datetime.fromisoformat(created_at_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="The page cursor is invalid.") from exc
        query = query.filter(
            or_(
                PolicyDocument.created_at < created_at,
                and_(
                    PolicyDocument.created_at == created_at,
                    PolicyDocument.policy_document_id < policy_document_id,
                ),
            )
        )
    documents = query.order_by(
        PolicyDocument.created_at.desc(),
        PolicyDocument.policy_document_id.desc(),
    ).limit(limit + 1).all()
    next_cursor = None
    if len(documents) > limit:
        last = documents[limit - 1]
        next_cursor = encode_page_cursor(
            last.created_at.isoformat(),
            last.policy_document_id,
        )
        documents = documents[:limit]
    return documents, next_cursor


def list_policy_gaps_page(
    session: Session,
    policy_document_id: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[PolicyGap], str | None]:
    """Return a deterministic keyset page of uncovered policy controls."""
    query = (
        session.query(PolicyDocument, PolicyVersion, ControlItem)
        .join(
            PolicyVersion,
            and_(
                PolicyVersion.policy_document_id == PolicyDocument.policy_document_id,
                PolicyVersion.version_number == PolicyDocument.current_version_number,
                PolicyVersion.is_finalized.is_(True),
            ),
        )
        .join(
            PolicyControlMapping,
            PolicyControlMapping.policy_version_id == PolicyVersion.policy_version_id,
        )
        .join(ControlItem, ControlItem.control_item_id == PolicyControlMapping.control_item_id)
        .outerjoin(
            ControlEvidenceBinding,
            ControlEvidenceBinding.control_item_id == ControlItem.control_item_id,
        )
        .filter(ControlEvidenceBinding.binding_id.is_(None))
    )
    if policy_document_id:
        query = query.filter(PolicyDocument.policy_document_id == policy_document_id)
    if cursor:
        created_at_text, document_id, framework, catalog_identifier = decode_page_cursor(
            cursor, 4
        )
        try:
            created_at = datetime.fromisoformat(created_at_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="The page cursor is invalid.") from exc
        query = query.filter(
            or_(
                PolicyDocument.created_at < created_at,
                and_(
                    PolicyDocument.created_at == created_at,
                    PolicyDocument.policy_document_id < document_id,
                ),
                and_(
                    PolicyDocument.created_at == created_at,
                    PolicyDocument.policy_document_id == document_id,
                    ControlItem.framework_key > framework,
                ),
                and_(
                    PolicyDocument.created_at == created_at,
                    PolicyDocument.policy_document_id == document_id,
                    ControlItem.framework_key == framework,
                    ControlItem.catalog_identifier > catalog_identifier,
                ),
            )
        )
    rows = query.order_by(
        PolicyDocument.created_at.desc(),
        PolicyDocument.policy_document_id.desc(),
        ControlItem.framework_key.asc(),
        ControlItem.catalog_identifier.asc(),
    ).limit(limit + 1).all()
    next_cursor = None
    if len(rows) > limit:
        last_document, last_version, last_item = rows[limit - 1]
        next_cursor = encode_page_cursor(
            last_document.created_at.isoformat(),
            last_document.policy_document_id,
            last_item.framework_key,
            last_item.catalog_identifier,
        )
        rows = rows[:limit]
    gaps = [
        PolicyGap(
            policy_document_id=document.policy_document_id,
            policy_title=document.policy_title,
            version_number=version.version_number,
            framework=item.framework_key,
            catalog_identifier=item.catalog_identifier,
            control_title=item.control_title,
        )
        for document, version, item in rows
    ]
    return gaps, next_cursor


def list_policy_gaps(session: Session, policy_document_id: str | None) -> list[PolicyGap]:
    """Return latest-version mappings that have no control-evidence binding."""
    if policy_document_id:
        document = session.get(PolicyDocument, policy_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="That policy document is not on file.")
        documents = [document]
    else:
        documents = list(session.query(PolicyDocument).order_by(PolicyDocument.created_at.desc()).all())
    bound_ids = {
        row[0] for row in session.query(ControlEvidenceBinding.control_item_id).all()
    }
    gaps: list[PolicyGap] = []
    for document in documents:
        version = current_version(session, document)
        mappings = (
            session.query(PolicyControlMapping)
            .filter_by(policy_version_id=version.policy_version_id)
            .all()
        )
        for mapping in mappings:
            if mapping.control_item_id in bound_ids:
                continue
            item = session.get(ControlItem, mapping.control_item_id)
            if item is None:  # pragma: no cover
                continue
            gaps.append(
                PolicyGap(
                    policy_document_id=document.policy_document_id,
                    policy_title=document.policy_title,
                    version_number=version.version_number,
                    framework=item.framework_key,
                    catalog_identifier=item.catalog_identifier,
                    control_title=item.control_title,
                )
            )
    return gaps


def serialize_policy(session: Session, document: PolicyDocument) -> dict[str, Any]:
    """Serialize a policy document with its latest edition and official mappings."""
    version = current_version(session, document)
    mappings = (
        session.query(PolicyControlMapping)
        .filter_by(policy_version_id=version.policy_version_id)
        .order_by(PolicyControlMapping.control_item_id)
        .all()
    )
    mapped: list[dict[str, str]] = []
    for mapping in mappings:
        item = session.get(ControlItem, mapping.control_item_id)
        if item is None:  # pragma: no cover
            continue
        mapped.append(
            {
                "framework": item.framework_key,
                "catalog_identifier": item.catalog_identifier,
                "control_title": item.control_title,
            }
        )
    return {
        "policy_document_id": document.policy_document_id,
        "policy_title": document.policy_title,
        "current_version": {
            "policy_version_id": version.policy_version_id,
            "version_number": version.version_number,
            "policy_body": version.policy_body,
            "mapped_controls": mapped,
        },
        "next_action": "Review policy gaps and attach the next evidence.",
    }


def serialize_gap(gap: PolicyGap) -> dict[str, Any]:
    """Serialize one uncovered policy/control gap."""
    return {
        "policy_document_id": gap.policy_document_id,
        "policy_title": gap.policy_title,
        "version_number": gap.version_number,
        "framework": gap.framework,
        "catalog_identifier": gap.catalog_identifier,
        "control_title": gap.control_title,
    }


def _allocate_next_version_number(
    session: Session,
    document: PolicyDocument,
) -> int:
    """Advance a policy revision counter only when the caller holds the current value."""
    expected_number = document.current_version_number
    next_number = expected_number + 1
    result = session.execute(
        update(PolicyDocument)
        .where(
            PolicyDocument.policy_document_id == document.policy_document_id,
            PolicyDocument.current_version_number == expected_number,
        )
        .values(current_version_number=next_number)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The policy changed concurrently. Reload it before publishing the next edition.",
        )
    document.current_version_number = next_number
    return next_number


def _write_version(
    session: Session,
    decision: AuthorizationDecision,
    document: PolicyDocument,
    version_number: int,
    policy_body: str,
    controls: list[ControlItem],
) -> PolicyVersion:
    """Persist mappings while an edition is open, then finalize it once."""
    version = PolicyVersion(
        policy_version_id=uuid4().hex,
        policy_document_id=document.policy_document_id,
        version_number=version_number,
        policy_body=policy_body,
        authored_by_actor=decision.actor_identifier,
        authored_at=datetime.now(timezone.utc).replace(tzinfo=None),
        is_finalized=False,
    )
    session.add(version)
    session.flush()
    seen: set[str] = set()
    for control in controls:
        if control.control_item_id in seen:
            continue
        seen.add(control.control_item_id)
        session.add(
            PolicyControlMapping(
                mapping_id=uuid4().hex,
                policy_version_id=version.policy_version_id,
                control_item_id=control.control_item_id,
            )
        )
    session.flush()
    version.is_finalized = True
    session.flush()
    return version
