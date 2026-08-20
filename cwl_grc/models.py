"""3NF SQLAlchemy objects for policies, official controls, and evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


LOCAL_DEVELOPMENT_TENANT = "local_development"


def _utc_now() -> datetime:
    """Return a naive UTC timestamp for existing database timestamp columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for GRC-owned tables."""


class ControlFramework(Base):
    """One published control catalog edition."""

    __tablename__ = "control_framework"

    framework_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    official_title: Mapped[str] = mapped_column(String(255), nullable=False)
    edition_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    control_items: Mapped[list[ControlItem]] = relationship(
        back_populates="control_framework"
    )


class ControlItem(Base):
    """One official control identifier inside a catalog edition."""

    __tablename__ = "control_item"
    __table_args__ = (
        UniqueConstraint(
            "framework_key",
            "catalog_identifier",
            name="control_item_catalog_identity",
        ),
    )

    control_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    framework_key: Mapped[str] = mapped_column(
        ForeignKey("control_framework.framework_key"),
        nullable=False,
    )
    catalog_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    control_title: Mapped[str] = mapped_column(String(255), nullable=False)
    control_statement: Mapped[str] = mapped_column(Text, nullable=False)
    control_framework: Mapped[ControlFramework] = relationship(
        back_populates="control_items"
    )
    evidence_bindings: Mapped[list[ControlEvidenceBinding]] = relationship(
        back_populates="control_item"
    )
    requirement_mappings: Mapped[list[ControlRequirementMapping]] = relationship(
        back_populates="control_item"
    )
    obligation_requirements: Mapped[list[ObligationRequirement]] = relationship(
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
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "evidence_record_id",
            name="evidence_record_tenant_identity",
        ),
    )

    evidence_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    evidence_title: Mapped[str] = mapped_column(String(255), nullable=False)
    collector_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(
        ForeignKey("authorization_purpose.purpose_code"),
        nullable=False,
    )
    ciphertext_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="legacy-v1",
        server_default="legacy-v1",
    )
    encryption_algorithm_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="fernet-v1-legacy",
        server_default="fernet-v1-legacy",
    )
    encryption_context_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    source_content_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    integrity_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    retention_class: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="standard",
        server_default="standard",
    )
    retention_started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utc_now,
        server_default="1970-01-01 00:00:00",
    )
    disposition_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    legal_hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_hold_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disposition_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evidence_bindings: Mapped[list[ControlEvidenceBinding]] = relationship(
        back_populates="evidence_record"
    )
    evidence_usages: Mapped[list[EvidenceUsage]] = relationship(
        back_populates="evidence_record"
    )


class ControlEvidenceBinding(Base):
    """Binds tenant-owned evidence to one official control identifier."""

    __tablename__ = "control_evidence_binding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "control_item_id",
            "evidence_record_id",
            name="control_evidence_binding_pair",
        ),
        UniqueConstraint(
            "tenant_id",
            "binding_id",
            name="control_evidence_binding_tenant_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_record_id"],
            ["evidence_record.tenant_id", "evidence_record.evidence_record_id"],
            name="control_evidence_binding_tenant_evidence",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    evidence_record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bound_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_code: Mapped[str] = mapped_column(
        ForeignKey("authorization_purpose.purpose_code"),
        nullable=False,
    )
    bound_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_item: Mapped[ControlItem] = relationship(back_populates="evidence_bindings")
    evidence_record: Mapped[EvidenceRecord] = relationship(
        back_populates="evidence_bindings"
    )
    evidence_usages: Mapped[list[EvidenceUsage]] = relationship(
        back_populates="legacy_binding",
        overlaps="evidence_record,evidence_usages,control_implementation,control_test_execution",
    )


class AuditEvent(Base):
    """Append-only record of an authorized tenant-scoped GRC action."""

    __tablename__ = "audit_event"

    audit_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
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
        UniqueConstraint(
            "tenant_id",
            "policy_document_id",
            name="policy_document_tenant_identity",
        ),
        CheckConstraint(
            "current_version_number >= 0",
            name="policy_document_version_nonnegative",
        ),
    )

    policy_document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    policy_title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_version_number: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    policy_versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy_document"
    )


class PolicyVersion(Base):
    """One immutable tenant-owned edition of a policy after finalization."""

    __tablename__ = "policy_version"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "policy_version_id",
            name="policy_version_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "policy_document_id",
            "version_number",
            name="policy_version_edition",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "policy_document_id"],
            ["policy_document.tenant_id", "policy_document.policy_document_id"],
            name="policy_version_tenant_document",
        ),
        CheckConstraint("version_number > 0", name="policy_version_number_positive"),
    )

    policy_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    policy_document_id: Mapped[str] = mapped_column(String(64), nullable=False)
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
    policy_document: Mapped[PolicyDocument] = relationship(
        back_populates="policy_versions"
    )
    policy_control_mappings: Mapped[list[PolicyControlMapping]] = relationship(
        back_populates="policy_version"
    )
    obligation_requirements: Mapped[list[ObligationRequirement]] = relationship(
        back_populates="policy_version", overlaps="obligation,requirements,internal_control_definition,control_implementation"
    )


class PolicyControlMapping(Base):
    """Maps one tenant-owned policy edition to one official catalog control."""

    __tablename__ = "policy_control_mapping"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "policy_version_id",
            "control_item_id",
            name="policy_control_mapping_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "policy_version_id"],
            ["policy_version.tenant_id", "policy_version.policy_version_id"],
            name="policy_control_mapping_tenant_version",
        ),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    policy_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    policy_version: Mapped[PolicyVersion] = relationship(
        back_populates="policy_control_mappings"
    )
    control_item: Mapped[ControlItem] = relationship()


class JurisdictionRecord(Base):
    """Tenant-owned reference to a jurisdiction without copying its legal body."""

    __tablename__ = "jurisdiction_record"
    __table_args__ = (
        UniqueConstraint("tenant_id", "jurisdiction_id", name="jurisdiction_record_tenant_identity"),
        UniqueConstraint("tenant_id", "jurisdiction_code", name="jurisdiction_record_tenant_code"),
    )

    jurisdiction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    jurisdiction_code: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction_name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(64), nullable=False)
    official_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligations: Mapped[list[ComplianceObligation]] = relationship(
        back_populates="jurisdiction"
    )


class RegulatorySource(Base):
    """Tenant-owned pointer to an authoritative legal or commitment source."""

    __tablename__ = "regulatory_source"
    __table_args__ = (
        UniqueConstraint("tenant_id", "regulatory_source_id", name="regulatory_source_tenant_identity"),
        UniqueConstraint("tenant_id", "source_code", name="regulatory_source_tenant_code"),
        CheckConstraint(
            "source_kind IN ('legislation', 'regulation', 'contract', 'voluntary', 'internal_mandate')",
            name="regulatory_source_kind",
        ),
        CheckConstraint(
            "license_classification IN ('identifier_only', 'lawfully_stored', 'restricted', 'unknown')",
            name="regulatory_source_license",
        ),
    )

    regulatory_source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    source_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(255), nullable=False)
    official_reference_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    license_classification: Mapped[str] = mapped_column(String(32), nullable=False)
    source_artifact_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revisions: Mapped[list[SourceRevision]] = relationship(back_populates="regulatory_source")


class SourceRevision(Base):
    """Immutable edition of an authoritative source with dates and digest."""

    __tablename__ = "source_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_revision_id", name="source_revision_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "regulatory_source_id", "revision_number", name="source_revision_edition"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "regulatory_source_id"],
            ["regulatory_source.tenant_id", "regulatory_source.regulatory_source_id"],
            name="source_revision_tenant_source",
        ),
        CheckConstraint("revision_number > 0", name="source_revision_number_positive"),
        CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= effective_from",
            name="source_revision_withdrawn_period",
        ),
        Index("source_revision_tenant_effective", "tenant_id", "effective_from"),
    )

    source_revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    regulatory_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_number: Mapped[int] = mapped_column(nullable=False)
    publication_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    immutable_artifact_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revision_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    regulatory_source: Mapped[RegulatorySource] = relationship(back_populates="revisions")
    obligations: Mapped[list[ComplianceObligation]] = relationship(
        back_populates="source_revision", overlaps="obligations,jurisdiction"
    )
    regulatory_changes: Mapped[list[RegulatoryChange]] = relationship(back_populates="source_revision")


class ComplianceObligation(Base):
    """Immutable tenant-scoped obligation derived from one source revision."""

    __tablename__ = "compliance_obligation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "compliance_obligation_id", name="compliance_obligation_tenant_identity"),
        UniqueConstraint("tenant_id", "obligation_code", name="compliance_obligation_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "source_revision_id"],
            ["source_revision.tenant_id", "source_revision.source_revision_id"],
            name="compliance_obligation_tenant_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "jurisdiction_id"],
            ["jurisdiction_record.tenant_id", "jurisdiction_record.jurisdiction_id"],
            name="compliance_obligation_tenant_jurisdiction",
        ),
        CheckConstraint(
            "obligation_type IN ('statutory', 'regulatory', 'contractual', 'voluntary', 'internal_mandate')",
            name="compliance_obligation_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="compliance_obligation_period",
        ),
        Index("compliance_obligation_tenant_effective", "tenant_id", "effective_from", "effective_to"),
    )

    compliance_obligation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    source_revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    obligation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    obligation_title: Mapped[str] = mapped_column(String(255), nullable=False)
    obligation_description: Mapped[str] = mapped_column(Text, nullable=False)
    obligation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_revision: Mapped[SourceRevision] = relationship(
        back_populates="obligations", overlaps="obligations,jurisdiction"
    )
    jurisdiction: Mapped[JurisdictionRecord | None] = relationship(
        back_populates="obligations", overlaps="obligations,source_revision"
    )
    requirements: Mapped[list[ObligationRequirement]] = relationship(
        back_populates="obligation", overlaps="obligation_requirements,policy_version,internal_control_definition,control_implementation"
    )
    applicability_rules: Mapped[list[ApplicabilityRule]] = relationship(back_populates="obligation")
    applicability_decisions: Mapped[list[ApplicabilityDecision]] = relationship(back_populates="obligation")
    legal_interpretations: Mapped[list[LegalInterpretation]] = relationship(back_populates="obligation")
    commitments: Mapped[list[ComplianceCommitment]] = relationship(back_populates="obligation")
    owner_assignments: Mapped[list[ObligationOwnerAssignment]] = relationship(back_populates="obligation")
    impact_assessments: Mapped[list[ChangeImpactAssessment]] = relationship(
        back_populates="obligation", overlaps="impact_assessments,regulatory_change"
    )


class ObligationRequirement(Base):
    """Reviewed relation from an obligation to a policy or internal control target."""

    __tablename__ = "obligation_requirement"
    __table_args__ = (
        UniqueConstraint("tenant_id", "obligation_requirement_id", name="obligation_requirement_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "compliance_obligation_id", "policy_version_id", "internal_control_definition_id",
            "control_implementation_id", name="obligation_requirement_target",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="obligation_requirement_tenant_obligation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "policy_version_id"],
            ["policy_version.tenant_id", "policy_version.policy_version_id"],
            name="obligation_requirement_tenant_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "internal_control_definition_id"],
            ["internal_control_definition.tenant_id", "internal_control_definition.internal_control_definition_id"],
            name="obligation_requirement_tenant_control",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="obligation_requirement_tenant_implementation",
        ),
        CheckConstraint(
            "policy_version_id IS NOT NULL OR internal_control_definition_id IS NOT NULL",
            name="obligation_requirement_target_present",
        ),
        CheckConstraint(
            "review_status = 'approved'",
            name="obligation_requirement_review",
        ),
    )

    obligation_requirement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    internal_control_definition_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_implementation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("control_item.control_item_id"), nullable=True
    )
    requirement_code: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="approved", server_default="approved")
    mapping_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(
        back_populates="requirements", overlaps="requirements,obligation_requirements,policy_version,internal_control_definition,control_implementation"
    )
    policy_version: Mapped[PolicyVersion | None] = relationship(
        back_populates="obligation_requirements", overlaps="obligation,requirements,internal_control_definition,control_implementation"
    )
    internal_control_definition: Mapped[InternalControlDefinition | None] = relationship(
        back_populates="obligation_requirements", overlaps="obligation,requirements,obligation_requirements,policy_version,control_implementation"
    )
    control_implementation: Mapped[ControlImplementation | None] = relationship(
        overlaps="obligation,requirements,obligation_requirements,policy_version,internal_control_definition"
    )
    control_item: Mapped[ControlItem | None] = relationship(back_populates="obligation_requirements")


class ApplicabilityRule(Base):
    """Versioned rule proposal used to evaluate an obligation for a scope."""

    __tablename__ = "applicability_rule"
    __table_args__ = (
        UniqueConstraint("tenant_id", "applicability_rule_id", name="applicability_rule_tenant_identity"),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="applicability_rule_tenant_obligation",
        ),
        CheckConstraint("active IN (TRUE, FALSE)", name="applicability_rule_active"),
    )

    applicability_rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_expression: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(back_populates="applicability_rules")
    decisions: Mapped[list[ApplicabilityDecision]] = relationship(
        back_populates="applicability_rule", overlaps="applicability_decisions,obligation"
    )


class ApplicabilityDecision(Base):
    """Immutable authorized applicability conclusion for one obligation and scope."""

    __tablename__ = "applicability_decision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "applicability_decision_id", name="applicability_decision_tenant_identity"),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="applicability_decision_tenant_obligation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "applicability_rule_id"],
            ["applicability_rule.tenant_id", "applicability_rule.applicability_rule_id"],
            name="applicability_decision_tenant_rule",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supersedes_decision_id"],
            ["applicability_decision.tenant_id", "applicability_decision.applicability_decision_id"],
            name="applicability_decision_tenant_supersession",
        ),
        CheckConstraint(
            "decision_code IN ('applicable', 'not_applicable', 'partially_applicable', 'inherited', 'compensating_control', 'pending_review', 'unknown')",
            name="applicability_decision_code",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="applicability_decision_period",
        ),
        Index("applicability_decision_tenant_review", "tenant_id", "next_review_at"),
    )

    applicability_decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    applicability_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supersedes_decision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_code: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(
        back_populates="applicability_decisions", overlaps="decisions,applicability_rule"
    )
    applicability_rule: Mapped[ApplicabilityRule | None] = relationship(
        back_populates="decisions", overlaps="applicability_decisions,obligation"
    )


class LegalInterpretation(Base):
    """Immutable interpretation reference that records authority without legal advice."""

    __tablename__ = "legal_interpretation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_interpretation_id", name="legal_interpretation_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "compliance_obligation_id", "interpretation_number", name="legal_interpretation_version"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="legal_interpretation_tenant_obligation",
        ),
    )

    legal_interpretation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    interpretation_number: Mapped[int] = mapped_column(nullable=False)
    interpretation_text: Mapped[str] = mapped_column(Text, nullable=False)
    authority_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    interpreted_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    interpreted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(back_populates="legal_interpretations")


class ComplianceCommitment(Base):
    """Contractual or voluntary commitment kept separate from statutory sources."""

    __tablename__ = "compliance_commitment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "compliance_commitment_id", name="compliance_commitment_tenant_identity"),
        UniqueConstraint("tenant_id", "commitment_code", name="compliance_commitment_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="compliance_commitment_tenant_obligation",
        ),
        CheckConstraint("commitment_type IN ('contract', 'voluntary')", name="compliance_commitment_type"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="compliance_commitment_period",
        ),
    )

    compliance_commitment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    commitment_code: Mapped[str] = mapped_column(String(64), nullable=False)
    commitment_title: Mapped[str] = mapped_column(String(255), nullable=False)
    commitment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    counterparty_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(back_populates="commitments")


class ObligationOwnerAssignment(Base):
    """Temporal owner assignment for an obligation, referencing an external identity."""

    __tablename__ = "obligation_owner_assignment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "obligation_owner_assignment_id", name="obligation_owner_tenant_identity"),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="obligation_owner_tenant_obligation",
        ),
        CheckConstraint("owner_kind IN ('accountable', 'legal', 'operator', 'reviewer')", name="obligation_owner_kind"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="obligation_owner_period"),
    )

    obligation_owner_assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    obligation: Mapped[ComplianceObligation] = relationship(back_populates="owner_assignments")


class RegulatoryChange(Base):
    """Immutable source-revision change intake that starts impact triage."""

    __tablename__ = "regulatory_change"
    __table_args__ = (
        UniqueConstraint("tenant_id", "regulatory_change_id", name="regulatory_change_tenant_identity"),
        UniqueConstraint("tenant_id", "change_code", name="regulatory_change_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "source_revision_id"],
            ["source_revision.tenant_id", "source_revision.source_revision_id"],
            name="regulatory_change_tenant_revision",
        ),
        CheckConstraint(
            "change_status = 'detected'",
            name="regulatory_change_status",
        ),
    )

    regulatory_change_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    source_revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    change_code: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_diff_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    change_status: Mapped[str] = mapped_column(String(32), nullable=False, default="detected", server_default="detected")
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_revision: Mapped[SourceRevision] = relationship(back_populates="regulatory_changes")
    impact_assessments: Mapped[list[ChangeImpactAssessment]] = relationship(
        back_populates="regulatory_change", overlaps="impact_assessments,obligation"
    )


class ChangeImpactAssessment(Base):
    """Immutable triage and re-approval action for one source change and obligation."""

    __tablename__ = "change_impact_assessment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "change_impact_assessment_id", name="change_impact_tenant_identity"),
        UniqueConstraint(
            "tenant_id", "regulatory_change_id", "compliance_obligation_id", "assessment_number",
            name="change_impact_assessment_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "regulatory_change_id"],
            ["regulatory_change.tenant_id", "regulatory_change.regulatory_change_id"],
            name="change_impact_tenant_change",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "compliance_obligation_id"],
            ["compliance_obligation.tenant_id", "compliance_obligation.compliance_obligation_id"],
            name="change_impact_tenant_obligation",
        ),
        CheckConstraint(
            "impact_status IN ('pending', 'no_change', 'policy_update', 'control_update', 'retire_obligation')",
            name="change_impact_status",
        ),
        CheckConstraint(
            "reapproval_status IN ('not_required', 'required', 'in_progress', 'complete')",
            name="change_impact_reapproval",
        ),
        CheckConstraint("due_at IS NULL OR due_at >= assessed_at", name="change_impact_due_period"),
    )

    change_impact_assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=LOCAL_DEVELOPMENT_TENANT, server_default=LOCAL_DEVELOPMENT_TENANT
    )
    regulatory_change_id: Mapped[str] = mapped_column(String(64), nullable=False)
    compliance_obligation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_number: Mapped[int] = mapped_column(nullable=False)
    impact_status: Mapped[str] = mapped_column(String(32), nullable=False)
    impact_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_owner_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    implementation_plan: Mapped[str] = mapped_column(Text, nullable=False)
    reapproval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    assessed_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    regulatory_change: Mapped[RegulatoryChange] = relationship(
        back_populates="impact_assessments", overlaps="impact_assessments,obligation"
    )
    obligation: Mapped[ComplianceObligation] = relationship(
        back_populates="impact_assessments", overlaps="impact_assessments,regulatory_change"
    )


class ControlObjective(Base):
    """Tenant-owned objective that groups organization-designed controls."""

    __tablename__ = "control_objective"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "objective_id",
            name="control_objective_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "objective_code",
            name="control_objective_tenant_code",
        ),
        Index("control_objective_tenant_created", "tenant_id", "created_at"),
    )

    objective_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    objective_code: Mapped[str] = mapped_column(String(64), nullable=False)
    objective_title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective_statement: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    internal_control_definitions: Mapped[list[InternalControlDefinition]] = relationship(
        back_populates="control_objective"
    )


class InternalControlDefinition(Base):
    """Reusable tenant-owned definition of an organization-designed control."""

    __tablename__ = "internal_control_definition"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "internal_control_definition_id",
            name="internal_control_definition_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "control_code",
            name="internal_control_definition_tenant_code",
        ),
        CheckConstraint(
            "lifecycle_status IN ('draft', 'published', 'retired')",
            name="internal_control_definition_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["control_objective.tenant_id", "control_objective.objective_id"],
            name="internal_control_definition_tenant_objective",
        ),
        Index("internal_control_definition_tenant_status", "tenant_id", "lifecycle_status"),
    )

    internal_control_definition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    objective_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_code: Mapped[str] = mapped_column(String(64), nullable=False)
    control_name: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_objective: Mapped[ControlObjective] = relationship(
        back_populates="internal_control_definitions"
    )
    definition_versions: Mapped[list[ControlDefinitionVersion]] = relationship(
        back_populates="internal_control_definition"
    )
    implementations: Mapped[list[ControlImplementation]] = relationship(
        back_populates="internal_control_definition"
    )
    owner_assignments: Mapped[list[ControlOwnerAssignment]] = relationship(
        back_populates="internal_control_definition"
    )
    requirement_mappings: Mapped[list[ControlRequirementMapping]] = relationship(
        back_populates="internal_control_definition"
    )
    obligation_requirements: Mapped[list[ObligationRequirement]] = relationship(
        back_populates="internal_control_definition", overlaps="obligation_requirements,obligation,requirements,policy_version,control_implementation"
    )


class ControlDefinitionVersion(Base):
    """Immutable effective-period revision of one internal control definition."""

    __tablename__ = "control_definition_version"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "control_definition_version_id",
            name="control_definition_version_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "internal_control_definition_id",
            "version_number",
            name="control_definition_version_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "internal_control_definition_id"],
            [
                "internal_control_definition.tenant_id",
                "internal_control_definition.internal_control_definition_id",
            ],
            name="control_definition_version_tenant_definition",
        ),
        CheckConstraint("version_number > 0", name="control_definition_version_positive"),
        CheckConstraint(
            "control_type IN ('preventive', 'detective', 'corrective')",
            name="control_definition_version_type",
        ),
        CheckConstraint(
            "execution_mode IN ('manual', 'automated', 'hybrid')",
            name="control_definition_version_mode",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="control_definition_version_period",
        ),
        Index(
            "control_definition_version_tenant_period",
            "tenant_id",
            "effective_from",
            "effective_to",
        ),
    )

    control_definition_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    internal_control_definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    control_statement: Mapped[str] = mapped_column(Text, nullable=False)
    control_type: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    frequency: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    internal_control_definition: Mapped[InternalControlDefinition] = relationship(
        back_populates="definition_versions"
    )
    test_plans: Mapped[list[ControlTestPlan]] = relationship(
        back_populates="control_definition_version",
        overlaps="control_implementation,test_plans",
    )


class ControlImplementation(Base):
    """Scoped deployment of one reusable internal control definition."""

    __tablename__ = "control_implementation"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "control_implementation_id",
            name="control_implementation_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "internal_control_definition_id",
            "scope_type",
            "scope_reference",
            name="control_implementation_scope_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "internal_control_definition_id"],
            [
                "internal_control_definition.tenant_id",
                "internal_control_definition.internal_control_definition_id",
            ],
            name="control_implementation_tenant_definition",
        ),
        CheckConstraint(
            "scope_type IN ('application', 'process', 'organization', 'data_asset', 'provider', 'inherited_service')",
            name="control_implementation_scope_type",
        ),
        CheckConstraint(
            "implementation_status IN ('planned', 'implemented', 'retired')",
            name="control_implementation_status",
        ),
        Index("control_implementation_tenant_status", "tenant_id", "implementation_status"),
    )

    control_implementation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    internal_control_definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    implementation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planned",
        server_default="planned",
    )
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    internal_control_definition: Mapped[InternalControlDefinition] = relationship(
        back_populates="implementations"
    )
    owner_assignments: Mapped[list[ControlOwnerAssignment]] = relationship(
        back_populates="control_implementation",
        overlaps="internal_control_definition,owner_assignments",
    )
    test_plans: Mapped[list[ControlTestPlan]] = relationship(
        back_populates="control_implementation",
        overlaps="control_definition_version,test_plans",
    )
    test_executions: Mapped[list[ControlTestExecution]] = relationship(
        back_populates="control_implementation",
        overlaps="control_test_plan,test_executions",
    )
    exceptions: Mapped[list[ControlException]] = relationship(
        back_populates="control_implementation"
    )
    deficiencies: Mapped[list[ControlDeficiency]] = relationship(
        back_populates="control_implementation",
        overlaps="control_test_execution,deficiencies",
    )
    evidence_usages: Mapped[list[EvidenceUsage]] = relationship(
        back_populates="control_implementation",
        overlaps="evidence_record,evidence_usages,control_test_execution",
    )


class ControlOwnerAssignment(Base):
    """Temporal accountable, operator, or reviewer assignment for an implementation."""

    __tablename__ = "control_owner_assignment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "internal_control_definition_id"],
            [
                "internal_control_definition.tenant_id",
                "internal_control_definition.internal_control_definition_id",
            ],
            name="control_owner_assignment_tenant_definition",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="control_owner_assignment_tenant_implementation",
        ),
        CheckConstraint(
            "owner_kind IN ('accountable', 'operator', 'reviewer')",
            name="control_owner_assignment_kind",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="control_owner_assignment_period",
        ),
        Index("control_owner_assignment_tenant_period", "tenant_id", "valid_from", "valid_to"),
    )

    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    internal_control_definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_implementation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    internal_control_definition: Mapped[InternalControlDefinition] = relationship(
        back_populates="owner_assignments",
        overlaps="control_implementation,owner_assignments",
    )
    control_implementation: Mapped[ControlImplementation | None] = relationship(
        back_populates="owner_assignments",
        overlaps="internal_control_definition,owner_assignments",
    )


class ControlRequirementMapping(Base):
    """Reviewed many-to-many relation between an internal control and external requirement."""

    __tablename__ = "control_requirement_mapping"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "internal_control_definition_id",
            "control_item_id",
            "relation_type",
            "valid_from",
            name="control_requirement_mapping_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "internal_control_definition_id"],
            [
                "internal_control_definition.tenant_id",
                "internal_control_definition.internal_control_definition_id",
            ],
            name="control_requirement_mapping_tenant_definition",
        ),
        CheckConstraint(
            "relation_type IN ('equivalent_to', 'subset_of', 'superset_of', 'intersects_with')",
            name="control_requirement_mapping_relation",
        ),
        CheckConstraint(
            "review_status IN ('proposed', 'approved', 'rejected')",
            name="control_requirement_mapping_review",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="control_requirement_mapping_period",
        ),
        Index("control_requirement_mapping_tenant_review", "tenant_id", "review_status"),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    internal_control_definition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="proposed",
        server_default="proposed",
    )
    mapping_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    internal_control_definition: Mapped[InternalControlDefinition] = relationship(
        back_populates="requirement_mappings"
    )
    control_item: Mapped[ControlItem] = relationship(back_populates="requirement_mappings")


class ControlTestPlan(Base):
    """Versioned plan for design or operating effectiveness testing."""

    __tablename__ = "control_test_plan"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "test_plan_id",
            name="control_test_plan_tenant_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_definition_version_id"],
            [
                "control_definition_version.tenant_id",
                "control_definition_version.control_definition_version_id",
            ],
            name="control_test_plan_tenant_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="control_test_plan_tenant_implementation",
        ),
        CheckConstraint(
            "effectiveness_type IN ('design', 'operating')",
            name="control_test_plan_effectiveness",
        ),
        CheckConstraint(
            "active IN (TRUE, FALSE)",
            name="control_test_plan_active",
        ),
        Index("control_test_plan_tenant_due", "tenant_id", "next_test_due_at"),
    )

    test_plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    control_definition_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_implementation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    effectiveness_type: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    sample_population: Mapped[str] = mapped_column(Text, nullable=False)
    test_frequency: Mapped[str] = mapped_column(String(64), nullable=False)
    next_test_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_definition_version: Mapped[ControlDefinitionVersion] = relationship(
        back_populates="test_plans",
        overlaps="control_implementation,test_plans",
    )
    control_implementation: Mapped[ControlImplementation] = relationship(
        back_populates="test_plans",
        overlaps="control_definition_version,test_plans",
    )
    test_executions: Mapped[list[ControlTestExecution]] = relationship(
        back_populates="control_test_plan",
        overlaps="control_implementation,control_test_plan",
    )


class ControlTestExecution(Base):
    """Historical execution of one control test plan over a defined period."""

    __tablename__ = "control_test_execution"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "test_execution_id",
            name="control_test_execution_tenant_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_plan_id"],
            ["control_test_plan.tenant_id", "control_test_plan.test_plan_id"],
            name="control_test_execution_tenant_plan",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="control_test_execution_tenant_implementation",
        ),
        CheckConstraint(
            "test_period_end >= test_period_start",
            name="control_test_execution_period",
        ),
        CheckConstraint(
            "execution_status IN ('planned', 'in_progress', 'completed', 'cancelled')",
            name="control_test_execution_status",
        ),
        Index("control_test_execution_tenant_period", "tenant_id", "test_period_end"),
    )

    test_execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    test_plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_implementation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    test_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    test_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    performed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sample_description: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_test_plan: Mapped[ControlTestPlan] = relationship(
        back_populates="test_executions",
        overlaps="control_implementation,test_executions",
    )
    control_implementation: Mapped[ControlImplementation] = relationship(
        back_populates="test_executions",
        overlaps="control_test_plan,test_executions",
    )
    test_result: Mapped[ControlTestResult | None] = relationship(
        back_populates="control_test_execution",
        uselist=False,
    )
    evidence_usages: Mapped[list[EvidenceUsage]] = relationship(
        back_populates="control_test_execution",
        overlaps="evidence_record,evidence_usages,control_implementation",
    )
    deficiencies: Mapped[list[ControlDeficiency]] = relationship(
        back_populates="control_test_execution",
        overlaps="control_implementation,deficiencies",
    )


class ControlTestResult(Base):
    """Immutable design or operating effectiveness conclusion for a test execution."""

    __tablename__ = "control_test_result"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "test_execution_id",
            name="control_test_result_execution_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_execution_id"],
            ["control_test_execution.tenant_id", "control_test_execution.test_execution_id"],
            name="control_test_result_tenant_execution",
        ),
        CheckConstraint(
            "result_code IN ('effective', 'ineffective', 'not_tested', 'not_applicable')",
            name="control_test_result_code",
        ),
        Index("control_test_result_tenant_determined", "tenant_id", "determined_at"),
    )

    test_result_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    test_execution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result_code: Mapped[str] = mapped_column(String(32), nullable=False)
    result_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    determined_by: Mapped[str] = mapped_column(String(128), nullable=False)
    determined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_test_execution: Mapped[ControlTestExecution] = relationship(
        back_populates="test_result"
    )


class ControlException(Base):
    """Time-bounded approved exception for one scoped control implementation."""

    __tablename__ = "control_exception"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="control_exception_tenant_implementation",
        ),
        CheckConstraint(
            "exception_status IN ('open', 'approved', 'expired', 'closed')",
            name="control_exception_status",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="control_exception_period",
        ),
        Index("control_exception_tenant_period", "tenant_id", "valid_from", "valid_to"),
    )

    exception_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    control_implementation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exception_reason: Mapped[str] = mapped_column(Text, nullable=False)
    exception_status: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_implementation: Mapped[ControlImplementation] = relationship(
        back_populates="exceptions"
    )


class ControlDeficiency(Base):
    """Open or resolved deficiency raised by a control test or reviewer."""

    __tablename__ = "control_deficiency"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="control_deficiency_tenant_implementation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_execution_id"],
            ["control_test_execution.tenant_id", "control_test_execution.test_execution_id"],
            name="control_deficiency_tenant_execution",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="control_deficiency_severity",
        ),
        CheckConstraint(
            "deficiency_status IN ('open', 'remediated', 'accepted')",
            name="control_deficiency_status",
        ),
        Index("control_deficiency_tenant_status", "tenant_id", "deficiency_status"),
    )

    deficiency_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    control_implementation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    test_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deficiency_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    deficiency_description: Mapped[str] = mapped_column(Text, nullable=False)
    deficiency_status: Mapped[str] = mapped_column(String(32), nullable=False)
    identified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    control_implementation: Mapped[ControlImplementation] = relationship(
        back_populates="deficiencies",
        overlaps="control_test_execution,deficiencies",
    )
    control_test_execution: Mapped[ControlTestExecution | None] = relationship(
        back_populates="deficiencies",
        overlaps="control_implementation,deficiencies",
    )


class EvidenceUsage(Base):
    """Purpose-approved use of evidence by a control implementation or test."""

    __tablename__ = "evidence_usage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "evidence_record_id",
            "control_test_execution_id",
            "purpose_code",
            name="evidence_usage_test_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_record_id"],
            ["evidence_record.tenant_id", "evidence_record.evidence_record_id"],
            name="evidence_usage_tenant_evidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_implementation_id"],
            ["control_implementation.tenant_id", "control_implementation.control_implementation_id"],
            name="evidence_usage_tenant_implementation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "control_test_execution_id"],
            ["control_test_execution.tenant_id", "control_test_execution.test_execution_id"],
            name="evidence_usage_tenant_execution",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "legacy_binding_id"],
            [
                "control_evidence_binding.tenant_id",
                "control_evidence_binding.binding_id",
            ],
            name="evidence_usage_tenant_legacy_binding",
        ),
        CheckConstraint(
            "usage_status IN ('unassessed', 'supporting', 'insufficient', 'rejected')",
            name="evidence_usage_status",
        ),
        CheckConstraint(
            "(legacy_binding_id IS NOT NULL AND control_implementation_id IS NULL AND control_test_execution_id IS NULL AND usage_status = 'unassessed') OR "
            "(legacy_binding_id IS NULL AND control_implementation_id IS NOT NULL AND control_test_execution_id IS NOT NULL AND usage_status <> 'unassessed')",
            name="evidence_usage_legacy_or_test",
        ),
        Index("evidence_usage_tenant_used", "tenant_id", "used_at"),
    )

    evidence_usage_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=LOCAL_DEVELOPMENT_TENANT,
        server_default=LOCAL_DEVELOPMENT_TENANT,
    )
    evidence_record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_implementation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_test_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legacy_binding_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    purpose_code: Mapped[str] = mapped_column(
        ForeignKey("authorization_purpose.purpose_code"),
        nullable=False,
    )
    usage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_note: Mapped[str] = mapped_column(Text, nullable=False)
    used_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evidence_record: Mapped[EvidenceRecord] = relationship(
        back_populates="evidence_usages",
        overlaps="control_implementation,evidence_usages,control_test_execution",
    )
    control_implementation: Mapped[ControlImplementation | None] = relationship(
        back_populates="evidence_usages",
        overlaps="evidence_record,evidence_usages,control_test_execution",
    )
    control_test_execution: Mapped[ControlTestExecution | None] = relationship(
        back_populates="evidence_usages",
        overlaps="control_implementation,evidence_record,evidence_usages",
    )
    legacy_binding: Mapped[ControlEvidenceBinding | None] = relationship(
        back_populates="evidence_usages",
        overlaps="evidence_record,evidence_usages,control_implementation,control_test_execution",
    )
