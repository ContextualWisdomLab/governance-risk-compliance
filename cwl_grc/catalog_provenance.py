"""Lawful catalog source registration and immutable import provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cwl_grc.authorization import AuthorizationDecision, PurposeCode
from cwl_grc.models import (
    CatalogImportReceipt,
    CatalogImportRun,
    CatalogRelease,
    SourceArtifact,
    SourceArtifactVersion,
    SourceLicensePolicy,
)


MAX_SOURCE_ARTIFACT_BYTES = 50 * 1024 * 1024
"""Maximum registered source size; raw source bytes are not stored by this slice."""

DEFAULT_CATALOG_SOURCE_HOSTS = frozenset(
    {
        "aicpa-cima.com",
        "csrc.nist.gov",
        "doi.org",
        "isms-p.or.kr",
        "isms.kisa.or.kr",
        "iso.org",
        "pages.nist.gov",
        "www.coso.org",
    }
)
"""Reviewed official hosts accepted by the HTTP catalog-provenance boundary."""

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MEDIA_TYPES = frozenset(
    {"application/json", "application/xml", "application/yaml", "text/plain"}
)
_CONTENT_CLASSES = frozenset(
    {
        "source_text",
        "licensed_text",
        "organization_summary",
        "translated_summary",
        "identifier_only",
    }
)
_CONTENT_CLASS_POLICIES = {
    "source_text": frozenset({"lawful_source_text"}),
    "licensed_text": frozenset({"licensed_no_redistribution"}),
    "organization_summary": frozenset({"organization_summary"}),
    "translated_summary": frozenset({"translated_summary"}),
    "identifier_only": frozenset({"identifier_only"}),
}


@dataclass(frozen=True)
class CatalogImportResult:
    """Return the durable import run, receipt, and idempotence outcome."""

    run: CatalogImportRun
    receipt: CatalogImportReceipt
    created: bool


def seed_source_license_policies(session: Session) -> None:
    """Seed explicit source classifications without copying any external text."""
    policies = (
        (
            "identifier_only",
            "Identifier-only source reference",
            False,
            False,
            True,
        ),
        (
            "lawful_source_text",
            "Lawfully stored and redistributable source text",
            True,
            True,
            True,
        ),
        (
            "licensed_no_redistribution",
            "Lawfully stored licensed text without redistribution",
            True,
            False,
            True,
        ),
        (
            "organization_summary",
            "Organization-authored summary",
            True,
            True,
            True,
        ),
        (
            "translated_summary",
            "Organization-authored translated summary",
            True,
            True,
            True,
        ),
    )
    now = _utc_now()
    for code, label, storage, export, identifier_export in policies:
        if session.get(SourceLicensePolicy, code) is not None:
            continue
        session.add(
            SourceLicensePolicy(
                license_policy_code=code,
                policy_label=label,
                policy_version="1",
                source_text_storage_allowed=storage,
                source_text_export_allowed=export,
                identifier_export_allowed=identifier_export,
                reviewed_by_actor="system_catalog_governance",
                reviewed_at=now,
            )
        )


def register_source_artifact(
    session: Session,
    decision: AuthorizationDecision,
    *,
    publisher_name: str,
    source_reference: str,
    source_url: str,
    artifact_content_class: str,
    license_policy_code: str,
    allowed_source_hosts: set[str],
) -> SourceArtifact:
    """Register an allowlisted HTTPS source pointer without fetching its bytes."""
    _require_catalog_purpose(decision)
    publisher_name = _required_text(publisher_name, "publisher name")
    source_reference = _required_text(source_reference, "source reference")
    source_url = _required_text(source_url, "source URL")
    content_class = _controlled_text(
        artifact_content_class, _CONTENT_CLASSES, "artifact content class"
    )
    source_host = _validated_source_host(source_url, allowed_source_hosts)
    policy = session.get(SourceLicensePolicy, license_policy_code)
    if policy is None:
        raise HTTPException(status_code=422, detail="The license policy is not registered.")
    if license_policy_code not in _CONTENT_CLASS_POLICIES[content_class]:
        raise HTTPException(
            status_code=422,
            detail="The license policy must match the artifact content class.",
        )
    existing = (
        session.query(SourceArtifact)
        .filter_by(publisher_name=publisher_name, source_reference=source_reference)
        .one_or_none()
    )
    if existing is not None:
        if existing.source_url != source_url or existing.license_policy_code != license_policy_code:
            raise HTTPException(
                status_code=409,
                detail="That source reference already has a different immutable pointer.",
            )
        return existing
    artifact = SourceArtifact(
        source_artifact_id=uuid4().hex,
        publisher_name=publisher_name,
        source_reference=source_reference,
        source_url=source_url,
        source_host=source_host,
        artifact_content_class=content_class,
        license_policy_code=license_policy_code,
        created_at=_utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(artifact)
            session.flush()
    except IntegrityError:
        existing = (
            session.query(SourceArtifact)
            .filter_by(publisher_name=publisher_name, source_reference=source_reference)
            .one_or_none()
        )
        if existing is None:
            raise
        if existing.source_url != source_url or existing.license_policy_code != license_policy_code:
            raise HTTPException(
                status_code=409,
                detail="That source reference already has a different immutable pointer.",
            )
        return existing
    return artifact


def register_source_artifact_version(
    session: Session,
    decision: AuthorizationDecision,
    source_artifact_id: str,
    *,
    edition_label: str,
    content_digest: str,
    media_type: str,
    byte_length: int,
    publication_date: date | None = None,
    effective_date: date | None = None,
    withdrawal_date: date | None = None,
) -> SourceArtifactVersion:
    """Register one exact digest and edition while retaining no raw source bytes."""
    _require_catalog_purpose(decision)
    artifact = session.get(SourceArtifact, source_artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="That source artifact is not registered.")
    edition_label = _required_text(edition_label, "edition label")
    content_digest = _validated_digest(content_digest)
    media_type = _validated_media_type(media_type)
    if not isinstance(byte_length, int) or isinstance(byte_length, bool):
        raise ValueError("byte length must be an integer.")
    if byte_length <= 0 or byte_length > MAX_SOURCE_ARTIFACT_BYTES:
        raise ValueError(f"byte length must be between 1 and {MAX_SOURCE_ARTIFACT_BYTES}.")
    if effective_date and publication_date and effective_date < publication_date:
        raise ValueError("effective date cannot precede publication date.")
    if withdrawal_date and publication_date and withdrawal_date < publication_date:
        raise ValueError("withdrawal date cannot precede publication date.")
    if withdrawal_date and effective_date and withdrawal_date < effective_date:
        raise ValueError("withdrawal date cannot precede effective date.")
    existing = (
        session.query(SourceArtifactVersion)
        .filter_by(source_artifact_id=source_artifact_id, content_digest=content_digest)
        .one_or_none()
    )
    if existing is not None:
        _assert_same_version(
            existing,
            edition_label,
            media_type,
            byte_length,
            publication_date,
            effective_date,
            withdrawal_date,
        )
        return existing
    version = SourceArtifactVersion(
        source_artifact_version_id=uuid4().hex,
        source_artifact_id=artifact.source_artifact_id,
        edition_label=edition_label,
        publication_date=publication_date,
        effective_date=effective_date,
        withdrawal_date=withdrawal_date,
        content_digest=content_digest,
        media_type=media_type,
        byte_length=byte_length,
        version_status="registered",
        registered_at=_utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(version)
            session.flush()
    except IntegrityError:
        existing = (
            session.query(SourceArtifactVersion)
            .filter_by(source_artifact_id=source_artifact_id, content_digest=content_digest)
            .one_or_none()
        )
        if existing is None:
            raise
        _assert_same_version(
            existing,
            edition_label,
            media_type,
            byte_length,
            publication_date,
            effective_date,
            withdrawal_date,
        )
        return existing
    return version


def record_catalog_import(
    session: Session,
    decision: AuthorizationDecision,
    source_artifact_version_id: str,
    *,
    parser_version: str,
    importer_commit: str,
    run_status: str,
    requirement_count: int = 0,
    changed_requirement_count: int = 0,
    warning_count: int = 0,
    failure_code: str | None = None,
) -> CatalogImportResult:
    """Record one idempotent parser run and deterministic receipt for a digest."""
    _require_catalog_purpose(decision)
    version = session.get(SourceArtifactVersion, source_artifact_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="That source artifact version is not registered.")
    parser_version = _required_text(parser_version, "parser version")
    importer_commit = _required_text(importer_commit, "importer commit")
    status = _controlled_text(run_status, {"succeeded", "failed"}, "import status")
    counts = (requirement_count, changed_requirement_count, warning_count)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
        raise ValueError("import counts must be non-negative integers.")
    if status == "failed" and not failure_code:
        raise ValueError("failed imports require a failure code.")
    if status == "succeeded" and failure_code:
        raise ValueError("succeeded imports cannot carry a failure code.")
    existing = (
        session.query(CatalogImportRun)
        .filter_by(
            source_artifact_version_id=source_artifact_version_id,
            parser_version=parser_version,
        )
        .one_or_none()
    )
    if existing is not None:
        existing_receipt = existing.receipt
        if existing_receipt is None:
            raise HTTPException(status_code=409, detail="The existing import has no receipt.")
        if (
            existing.run_status,
            existing.importer_commit,
            existing.failure_code,
            existing_receipt.requirement_count,
            existing_receipt.changed_requirement_count,
            existing_receipt.warning_count,
        ) != (
            status,
            importer_commit,
            failure_code,
            requirement_count,
            changed_requirement_count,
            warning_count,
        ):
            raise HTTPException(
                status_code=409,
                detail="That source digest already has an immutable parser receipt.",
            )
        return CatalogImportResult(existing, existing_receipt, False)
    now = _utc_now()
    run = CatalogImportRun(
        catalog_import_run_id=uuid4().hex,
        source_artifact_version_id=version.source_artifact_version_id,
        parser_version=parser_version,
        importer_commit=importer_commit,
        run_status=status,
        started_at=now,
        completed_at=now,
        failure_code=failure_code,
    )
    receipt_digest = _receipt_digest(
        version.content_digest,
        parser_version,
        requirement_count,
        changed_requirement_count,
        warning_count,
    )
    receipt = CatalogImportReceipt(
        catalog_import_receipt_id=uuid4().hex,
        catalog_import_run=run,
        requirement_count=requirement_count,
        changed_requirement_count=changed_requirement_count,
        warning_count=warning_count,
        receipt_digest=receipt_digest,
        generated_at=now,
    )
    try:
        with session.begin_nested():
            session.add(run)
            session.add(receipt)
            session.flush()
    except IntegrityError:
        existing = (
            session.query(CatalogImportRun)
            .filter_by(
                source_artifact_version_id=source_artifact_version_id,
                parser_version=parser_version,
            )
            .one_or_none()
        )
        if existing is None or existing.receipt is None:
            raise
        existing_receipt = existing.receipt
        if (
            existing.run_status,
            existing.importer_commit,
            existing.failure_code,
            existing_receipt.requirement_count,
            existing_receipt.changed_requirement_count,
            existing_receipt.warning_count,
        ) != (
            status,
            importer_commit,
            failure_code,
            requirement_count,
            changed_requirement_count,
            warning_count,
        ):
            raise HTTPException(
                status_code=409,
                detail="That source digest already has an immutable parser receipt.",
            )
        return CatalogImportResult(existing, existing_receipt, False)
    return CatalogImportResult(run, receipt, True)


def publish_catalog_release(
    session: Session,
    decision: AuthorizationDecision,
    source_artifact_version_id: str,
    *,
    release_key: str,
) -> CatalogRelease:
    """Publish a source version only after a successful import receipt exists."""
    _require_catalog_purpose(decision)
    version = session.get(SourceArtifactVersion, source_artifact_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="That source artifact version is not registered.")
    release_key = _required_text(release_key, "release key")
    successful = (
        session.query(CatalogImportRun)
        .join(
            CatalogImportReceipt,
            CatalogImportReceipt.catalog_import_run_id == CatalogImportRun.catalog_import_run_id,
        )
        .filter(
            CatalogImportRun.source_artifact_version_id == source_artifact_version_id,
            CatalogImportRun.run_status == "succeeded",
        )
        .order_by(
            CatalogImportRun.completed_at.desc(),
            CatalogImportRun.catalog_import_run_id.desc(),
        )
        .first()
    )
    if successful is None:
        raise HTTPException(status_code=409, detail="A successful import receipt is required first.")
    existing = (
        session.query(CatalogRelease)
        .filter_by(source_artifact_version_id=source_artifact_version_id, release_key=release_key)
        .one_or_none()
    )
    if existing is not None:
        return existing
    now = _utc_now()
    release = CatalogRelease(
        catalog_release_id=uuid4().hex,
        source_artifact_version_id=version.source_artifact_version_id,
        catalog_import_run_id=successful.catalog_import_run_id,
        release_key=release_key,
        release_status="published",
        created_at=now,
        published_at=now,
    )
    try:
        with session.begin_nested():
            session.add(release)
            session.flush()
    except IntegrityError:
        existing = (
            session.query(CatalogRelease)
            .filter_by(source_artifact_version_id=source_artifact_version_id, release_key=release_key)
            .one_or_none()
        )
        if existing is None:
            raise
        return existing
    return release


def source_text_export_allowed(policy: SourceLicensePolicy) -> bool:
    """Return the explicit source-text export decision; absence never defaults open."""
    return bool(policy.source_text_export_allowed)


def _require_catalog_purpose(decision: AuthorizationDecision) -> None:
    """Require the catalog-governance purpose for source lifecycle writes."""
    if decision.purpose_code is not PurposeCode.CATALOG_GOVERNANCE:
        raise HTTPException(status_code=403, detail="This action requires catalog_governance.")


def _required_text(value: str, label: str) -> str:
    """Return trimmed non-empty text for one catalog field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text.")
    return value.strip()


def _controlled_text(value: str, allowed: set[str] | frozenset[str], label: str) -> str:
    """Return one member of an explicit controlled vocabulary."""
    value = _required_text(value, label)
    if value not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}.")
    return value


def _validated_source_host(source_url: str, allowed_hosts: set[str]) -> str:
    """Validate an HTTPS pointer against an exact host allowlist without redirects."""
    source_url = _required_text(source_url, "source URL")
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source URL must be HTTPS without credentials.")
    if parsed.fragment:
        raise ValueError("source URL must not contain a fragment.")
    if parsed.port is not None and parsed.port != 443:
        raise ValueError("source URL must not contain a non-default port.")
    host = parsed.hostname.lower().rstrip(".")
    normalized_hosts = {str(item).lower().rstrip(".") for item in allowed_hosts}
    if host not in normalized_hosts:
        raise ValueError("source URL host is not allowlisted.")
    return host


def _validated_digest(value: str) -> str:
    """Require a lowercase SHA-256 digest rather than a mutable source label."""
    value = _required_text(value, "content digest")
    if not _SHA256.fullmatch(value):
        raise ValueError("content digest must be 64 lowercase hexadecimal characters.")
    return value


def _validated_media_type(value: str) -> str:
    """Allow only inert catalog media types without content parameters."""
    value = _required_text(value, "media type").lower()
    if value not in _ALLOWED_MEDIA_TYPES:
        raise ValueError("media type is not supported for catalog registration.")
    return value


def _assert_same_version(
    version: SourceArtifactVersion,
    edition_label: str,
    media_type: str,
    byte_length: int,
    publication_date: date | None,
    effective_date: date | None,
    withdrawal_date: date | None,
) -> None:
    """Reject a digest collision whose metadata differs from the first receipt."""
    if (
        version.edition_label != edition_label
        or version.media_type != media_type
        or version.byte_length != byte_length
        or version.publication_date != publication_date
        or version.effective_date != effective_date
        or version.withdrawal_date != withdrawal_date
    ):
        raise HTTPException(
            status_code=409,
            detail="That source digest already has different immutable metadata.",
        )


def _receipt_digest(
    content_digest: str,
    parser_version: str,
    requirement_count: int,
    changed_requirement_count: int,
    warning_count: int,
) -> str:
    """Hash the stable import result fields for reproducible receipt comparison."""
    payload = json.dumps(
        {
            "changed_requirement_count": changed_requirement_count,
            "content_digest": content_digest,
            "parser_version": parser_version,
            "requirement_count": requirement_count,
            "warning_count": warning_count,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> datetime:
    """Return the schema's naive UTC timestamp representation."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
