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
