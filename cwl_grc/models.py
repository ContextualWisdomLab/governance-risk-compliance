"""3NF SQLAlchemy objects for policies, official controls, and evidence."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for GRC-owned tables."""


class SourceLicensePolicy(Base):
    """Reviewed storage and export permissions for one source classification."""

    __tablename__ = "source_license_policy"
    __table_args__ = (
        CheckConstraint(
            "source_text_storage_allowed IN (TRUE, FALSE)",
            name="source_license_policy_storage_boolean",
        ),
        CheckConstraint(
            "source_text_export_allowed IN (TRUE, FALSE)",
            name="source_license_policy_export_boolean",
        ),
        CheckConstraint(
            "identifier_export_allowed IN (TRUE, FALSE)",
            name="source_license_policy_identifier_boolean",
        ),
    )

    license_policy_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_label: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_text_storage_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    source_text_export_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    identifier_export_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    reviewed_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_artifacts: Mapped[list[SourceArtifact]] = relationship(
        back_populates="license_policy"
    )


class SourceArtifact(Base):
    """Lawful pointer to a publisher artifact without copying its source bytes."""

    __tablename__ = "source_artifact"
    __table_args__ = (
        UniqueConstraint(
            "publisher_name",
            "source_reference",
            name="source_artifact_publisher_reference",
        ),
        CheckConstraint(
            "artifact_content_class IN ('source_text', 'licensed_text', 'organization_summary', 'translated_summary', 'identifier_only')",
            name="source_artifact_content_class",
        ),
        Index("source_artifact_publisher_created", "publisher_name", "created_at"),
    )

    source_artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publisher_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_host: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_content_class: Mapped[str] = mapped_column(String(32), nullable=False)
    license_policy_code: Mapped[str] = mapped_column(
        ForeignKey("source_license_policy.license_policy_code"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    license_policy: Mapped[SourceLicensePolicy] = relationship(
        back_populates="source_artifacts"
    )
    versions: Mapped[list[SourceArtifactVersion]] = relationship(
        back_populates="source_artifact"
    )


class SourceArtifactVersion(Base):
    """Immutable metadata for one exact source artifact digest and edition."""

    __tablename__ = "source_artifact_version"
    __table_args__ = (
        UniqueConstraint(
            "source_artifact_id",
            "content_digest",
            name="source_artifact_version_digest",
        ),
        CheckConstraint(
            "version_status IN ('registered', 'withdrawn')",
            name="source_artifact_version_status",
        ),
        CheckConstraint("byte_length > 0", name="source_artifact_version_size_positive"),
        Index(
            "source_artifact_version_artifact_date",
            "source_artifact_id",
            "effective_date",
        ),
    )

    source_artifact_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("source_artifact.source_artifact_id"), nullable=False
    )
    edition_label: Mapped[str] = mapped_column(String(128), nullable=False)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    withdrawal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    version_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="registered", server_default="registered"
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_artifact: Mapped[SourceArtifact] = relationship(back_populates="versions")
    import_runs: Mapped[list[CatalogImportRun]] = relationship(
        back_populates="source_artifact_version"
    )
    catalog_releases: Mapped[list[CatalogRelease]] = relationship(
        back_populates="source_artifact_version"
    )


class CatalogImportRun(Base):
    """Immutable receipt of a parser run keyed by source digest and parser version."""

    __tablename__ = "catalog_import_run"
    __table_args__ = (
        UniqueConstraint(
            "source_artifact_version_id",
            "parser_version",
            name="catalog_import_run_version_parser",
        ),
        CheckConstraint(
            "run_status IN ('succeeded', 'failed')",
            name="catalog_import_run_status",
        ),
        Index("catalog_import_run_status_created", "run_status", "started_at"),
    )

    catalog_import_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_artifact_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_artifact_version.source_artifact_version_id"), nullable=False
    )
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    importer_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    run_status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_artifact_version: Mapped[SourceArtifactVersion] = relationship(
        back_populates="import_runs"
    )
    receipt: Mapped[CatalogImportReceipt | None] = relationship(
        back_populates="catalog_import_run", uselist=False
    )
    catalog_releases: Mapped[list[CatalogRelease]] = relationship(
        back_populates="catalog_import_run"
    )


class CatalogImportReceipt(Base):
    """Immutable deterministic counts and digest for one completed catalog import."""

    __tablename__ = "catalog_import_receipt"
    __table_args__ = (
        UniqueConstraint(
            "catalog_import_run_id",
            name="catalog_import_receipt_run_identity",
        ),
        CheckConstraint(
            "requirement_count >= 0 AND changed_requirement_count >= 0 AND warning_count >= 0",
            name="catalog_import_receipt_counts_nonnegative",
        ),
    )

    catalog_import_receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_import_run_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_import_run.catalog_import_run_id"), nullable=False
    )
    requirement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_requirement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    catalog_import_run: Mapped[CatalogImportRun] = relationship(back_populates="receipt")


class CatalogRelease(Base):
    """Immutable published identity for one source artifact version."""

    __tablename__ = "catalog_release"
    __table_args__ = (
        UniqueConstraint(
            "source_artifact_version_id",
            "release_key",
            name="catalog_release_version_key",
        ),
        CheckConstraint(
            "release_status IN ('draft', 'published', 'withdrawn')",
            name="catalog_release_status",
        ),
        Index("catalog_release_status_created", "release_status", "created_at"),
    )

    catalog_release_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_artifact_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_artifact_version.source_artifact_version_id"), nullable=False
    )
    catalog_import_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_import_run.catalog_import_run_id"), nullable=True
    )
    release_key: Mapped[str] = mapped_column(String(128), nullable=False)
    release_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_artifact_version: Mapped[SourceArtifactVersion] = relationship(
        back_populates="catalog_releases"
    )
    catalog_import_run: Mapped[CatalogImportRun | None] = relationship(
        back_populates="catalog_releases"
    )
    frameworks: Mapped[list[ControlFramework]] = relationship(
        back_populates="catalog_release"
    )


class ControlFramework(Base):
    """One published control catalog edition."""

    __tablename__ = "control_framework"

    framework_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    official_title: Mapped[str] = mapped_column(String(255), nullable=False)
    edition_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    catalog_release_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_release.catalog_release_id"), nullable=True
    )
    control_items: Mapped[list[ControlItem]] = relationship(back_populates="control_framework")
    catalog_release: Mapped[CatalogRelease | None] = relationship(
        back_populates="frameworks"
    )


class ControlItem(Base):
    """One official control identifier inside a catalog edition."""

    __tablename__ = "control_item"
    __table_args__ = (
        UniqueConstraint("framework_key", "catalog_identifier", name="control_item_catalog_identity"),
    )

    control_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    framework_key: Mapped[str] = mapped_column(
        ForeignKey("control_framework.framework_key"),
        nullable=False,
    )
    catalog_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    control_title: Mapped[str] = mapped_column(String(255), nullable=False)
    control_statement: Mapped[str] = mapped_column(Text, nullable=False)
    control_framework: Mapped[ControlFramework] = relationship(back_populates="control_items")
    evidence_bindings: Mapped[list[ControlEvidenceBinding]] = relationship(
        back_populates="control_item"
    )


class AuthorizationPurpose(Base):
    """A purpose that may authorize evidence work."""

    __tablename__ = "authorization_purpose"

    purpose_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose_label: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose_description: Mapped[str] = mapped_column(Text, nullable=False)


class EvidenceRecord(Base):
    """One evidence artifact whose payload stays usable to authorized officers."""

    __tablename__ = "evidence_record"

    evidence_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evidence_title: Mapped[str] = mapped_column(String(255), nullable=False)
    collector_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(
        ForeignKey("authorization_purpose.purpose_code"),
        nullable=False,
    )
    ciphertext_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evidence_bindings: Mapped[list[ControlEvidenceBinding]] = relationship(
        back_populates="evidence_record"
    )


class ControlEvidenceBinding(Base):
    """Binds one evidence artifact to one official control identifier."""

    __tablename__ = "control_evidence_binding"
    __table_args__ = (
        UniqueConstraint(
            "control_item_id",
            "evidence_record_id",
            name="control_evidence_binding_pair",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    evidence_record_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_record.evidence_record_id"),
        nullable=False,
    )
    bound_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(
        ForeignKey("authorization_purpose.purpose_code"),
        nullable=False,
    )
    bound_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_item: Mapped[ControlItem] = relationship(back_populates="evidence_bindings")
    evidence_record: Mapped[EvidenceRecord] = relationship(back_populates="evidence_bindings")


class AuditEvent(Base):
    """Append-only record of an authorized GRC action."""

    __tablename__ = "audit_event"

    audit_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(64), nullable=False)
    action_name: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PolicyDocument(Base):
    """Stable identity and optimistic revision counter for one authored policy."""

    __tablename__ = "policy_document"
    __table_args__ = (
        CheckConstraint(
            "current_version_number >= 0",
            name="policy_document_version_nonnegative",
        ),
    )

    policy_document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_version_number: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    policy_versions: Mapped[list[PolicyVersion]] = relationship(back_populates="policy_document")


class PolicyVersion(Base):
    """One immutable edition of a policy document after finalization."""

    __tablename__ = "policy_version"
    __table_args__ = (
        UniqueConstraint("policy_document_id", "version_number", name="policy_version_edition"),
        CheckConstraint("version_number > 0", name="policy_version_number_positive"),
    )

    policy_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_document_id: Mapped[str] = mapped_column(
        ForeignKey("policy_document.policy_document_id"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    policy_body: Mapped[str] = mapped_column(Text, nullable=False)
    authored_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_finalized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    policy_document: Mapped[PolicyDocument] = relationship(back_populates="policy_versions")
    policy_control_mappings: Mapped[list[PolicyControlMapping]] = relationship(
        back_populates="policy_version"
    )


class PolicyControlMapping(Base):
    """Maps one policy edition to one official catalog control."""

    __tablename__ = "policy_control_mapping"
    __table_args__ = (
        UniqueConstraint(
            "policy_version_id",
            "control_item_id",
            name="policy_control_mapping_pair",
        ),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_version_id: Mapped[str] = mapped_column(
        ForeignKey("policy_version.policy_version_id"),
        nullable=False,
    )
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    policy_version: Mapped[PolicyVersion] = relationship(back_populates="policy_control_mappings")
    control_item: Mapped[ControlItem] = relationship()
