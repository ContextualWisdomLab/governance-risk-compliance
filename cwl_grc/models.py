"""3NF SQLAlchemy objects for policies, official controls, and evidence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


LOCAL_DEVELOPMENT_TENANT = "local_development"


class Base(DeclarativeBase):
    """Declarative base for GRC-owned tables."""


class ControlFramework(Base):
    """One published control catalog edition."""

    __tablename__ = "control_framework"

    framework_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    official_title: Mapped[str] = mapped_column(String(255), nullable=False)
    edition_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    control_items: Mapped[list[ControlItem]] = relationship(back_populates="control_framework")


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
    """One tenant-owned evidence artifact kept usable for authorized officers."""

    __tablename__ = "evidence_record"

    evidence_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
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
    """Binds tenant-owned evidence to one official control identifier."""

    __tablename__ = "control_evidence_binding"
    __table_args__ = (
        UniqueConstraint(
            "control_item_id",
            "evidence_record_id",
            name="control_evidence_binding_pair",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
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
    """Append-only record of an authorized tenant-scoped GRC action."""

    __tablename__ = "audit_event"

    audit_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    actor_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(64), nullable=False)
    action_name: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PolicyDocument(Base):
    """Stable tenant-owned identity and optimistic revision counter for one policy."""

    __tablename__ = "policy_document"
    __table_args__ = (
        CheckConstraint(
            "current_version_number >= 0",
            name="policy_document_version_nonnegative",
        ),
    )

    policy_document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
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
    """One immutable tenant-owned edition of a policy after finalization."""

    __tablename__ = "policy_version"
    __table_args__ = (
        UniqueConstraint("policy_document_id", "version_number", name="policy_version_edition"),
        CheckConstraint("version_number > 0", name="policy_version_number_positive"),
    )

    policy_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
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
    """Maps one tenant-owned policy edition to one official catalog control."""

    __tablename__ = "policy_control_mapping"
    __table_args__ = (
        UniqueConstraint(
            "policy_version_id",
            "control_item_id",
            name="policy_control_mapping_pair",
        ),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
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
