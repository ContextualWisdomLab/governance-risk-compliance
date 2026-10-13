"""3NF SQLAlchemy objects for policies, official controls, evidence, and audits."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class AuditProgram(Base):
    """A risk-based audit program planned for one period and approved by an audit authority."""

    __tablename__ = "audit_program"
    __table_args__ = (
        CheckConstraint(
            "program_status IN ('draft', 'approved')",
            name="audit_program_status_known",
        ),
        CheckConstraint("period_end >= period_start", name="audit_program_period_ordered"),
    )

    audit_program_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    program_title: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    risk_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    audit_authority_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    approved_by_actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    program_status: Mapped[str] = mapped_column(String(16), nullable=False)


class AuditEngagement(Base):
    """One audit engagement performed under an approved audit program."""

    __tablename__ = "audit_engagement"
    __table_args__ = (
        CheckConstraint(
            "engagement_status IN ('planned', 'fieldwork', 'reporting', 'closed')",
            name="audit_engagement_status_known",
        ),
        CheckConstraint("period_end >= period_start", name="audit_engagement_period_ordered"),
    )

    audit_engagement_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_program_id: Mapped[str] = mapped_column(
        ForeignKey("audit_program.audit_program_id"),
        nullable=False,
    )
    engagement_title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_statement: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    lead_auditor_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    engagement_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EngagementCriterion(Base):
    """An official external requirement used as an audit criterion for one engagement.

    ``internal_control_reference`` is an opaque, unvalidated placeholder for the
    future Issue #27 internal-control implementation link; it is not a foreign key.
    """

    __tablename__ = "engagement_criterion"
    __table_args__ = (
        UniqueConstraint(
            "audit_engagement_id",
            "control_item_id",
            name="engagement_criterion_pair",
        ),
    )

    engagement_criterion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_engagement_id: Mapped[str] = mapped_column(
        ForeignKey("audit_engagement.audit_engagement_id"),
        nullable=False,
    )
    control_item_id: Mapped[str] = mapped_column(
        ForeignKey("control_item.control_item_id"),
        nullable=False,
    )
    internal_control_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EngagementTeamMember(Base):
    """One auditor assigned to an engagement with a stated role and competence."""

    __tablename__ = "engagement_team_member"
    __table_args__ = (
        UniqueConstraint("audit_engagement_id", "auditor_actor", name="engagement_team_member_pair"),
        CheckConstraint(
            "team_role IN ('lead', 'auditor', 'supervisor')",
            name="engagement_team_member_role_known",
        ),
        CheckConstraint(
            "length(trim(competence_statement)) > 0",
            name="engagement_team_member_competence_stated",
        ),
    )

    engagement_team_member_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_engagement_id: Mapped[str] = mapped_column(
        ForeignKey("audit_engagement.audit_engagement_id"),
        nullable=False,
    )
    auditor_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    team_role: Mapped[str] = mapped_column(String(16), nullable=False)
    competence_statement: Mapped[str] = mapped_column(Text, nullable=False)


class IndependenceDeclaration(Base):
    """An immutable conflict-of-interest declaration; the highest number is current."""

    __tablename__ = "independence_declaration"
    __table_args__ = (
        UniqueConstraint(
            "audit_engagement_id",
            "auditor_actor",
            "declaration_number",
            name="independence_declaration_sequence",
        ),
        CheckConstraint("declaration_number > 0", name="independence_declaration_number_positive"),
    )

    independence_declaration_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_engagement_id: Mapped[str] = mapped_column(
        ForeignKey("audit_engagement.audit_engagement_id"),
        nullable=False,
    )
    auditor_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    declaration_number: Mapped[int] = mapped_column(nullable=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    declaration_statement: Mapped[str] = mapped_column(Text, nullable=False)
    declared_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditProcedure(Base):
    """A documented test of one criterion with a reproducible sample selection."""

    __tablename__ = "audit_procedure"
    __table_args__ = (
        CheckConstraint("population_size > 0", name="audit_procedure_population_positive"),
        CheckConstraint(
            "sample_size > 0 AND sample_size <= population_size",
            name="audit_procedure_sample_within_population",
        ),
        CheckConstraint(
            "selection_method IN ('seeded_random', 'judgmental', 'full_population')",
            name="audit_procedure_method_known",
        ),
    )

    audit_procedure_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_engagement_id: Mapped[str] = mapped_column(
        ForeignKey("audit_engagement.audit_engagement_id"),
        nullable=False,
    )
    engagement_criterion_id: Mapped[str] = mapped_column(
        ForeignKey("engagement_criterion.engagement_criterion_id"),
        nullable=False,
    )
    procedure_description: Mapped[str] = mapped_column(Text, nullable=False)
    population_description: Mapped[str] = mapped_column(Text, nullable=False)
    population_size: Mapped[int] = mapped_column(nullable=False)
    selection_method: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False)
    selection_seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditSampleItem(Base):
    """One selected 1-based population ordinal of an audit procedure."""

    __tablename__ = "audit_sample_item"
    __table_args__ = (
        UniqueConstraint("audit_procedure_id", "population_ordinal", name="audit_sample_item_ordinal"),
        CheckConstraint("population_ordinal >= 1", name="audit_sample_item_ordinal_positive"),
    )

    audit_sample_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_procedure_id: Mapped[str] = mapped_column(
        ForeignKey("audit_procedure.audit_procedure_id"),
        nullable=False,
    )
    population_ordinal: Mapped[int] = mapped_column(nullable=False)
    population_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exception_noted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    exception_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEvidenceLink(Base):
    """References an existing evidence record from exactly one procedure or sample item.

    Issue #27 ``evidence_usage`` is expected to supersede and absorb this table.
    Evidence plaintext is never copied here.
    """

    __tablename__ = "audit_evidence_link"
    __table_args__ = (
        CheckConstraint(
            "(audit_procedure_id IS NOT NULL AND audit_sample_item_id IS NULL) "
            "OR (audit_procedure_id IS NULL AND audit_sample_item_id IS NOT NULL)",
            name="audit_evidence_link_one_target",
        ),
    )

    audit_evidence_link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evidence_record_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_record.evidence_record_id"),
        nullable=False,
    )
    audit_procedure_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_procedure.audit_procedure_id"),
        nullable=True,
    )
    audit_sample_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_sample_item.audit_sample_item_id"),
        nullable=True,
    )
    linked_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditFinding(Base):
    """Stable identity, lifecycle status, and optimistic revision counter of a finding."""

    __tablename__ = "audit_finding"
    __table_args__ = (
        CheckConstraint(
            "finding_status IN ('open', 'remediation', 'retest_failed', 'closed', 'risk_accepted')",
            name="audit_finding_status_known",
        ),
        CheckConstraint("current_revision_number >= 0", name="audit_finding_revision_nonnegative"),
    )

    audit_finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_engagement_id: Mapped[str] = mapped_column(
        ForeignKey("audit_engagement.audit_engagement_id"),
        nullable=False,
    )
    finding_status: Mapped[str] = mapped_column(String(16), nullable=False)
    remediation_owner_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_revision_number: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditFindingRevision(Base):
    """One immutable, append-only edition of a finding's content and rating."""

    __tablename__ = "audit_finding_revision"
    __table_args__ = (
        UniqueConstraint("audit_finding_id", "revision_number", name="audit_finding_revision_edition"),
        CheckConstraint("revision_number > 0", name="audit_finding_revision_number_positive"),
        CheckConstraint(
            "severity_rating IN ('low', 'medium', 'high', 'critical')",
            name="audit_finding_revision_severity_known",
        ),
        CheckConstraint(
            "length(trim(rating_rationale)) > 0",
            name="audit_finding_revision_rationale_stated",
        ),
    )

    audit_finding_revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_finding_id: Mapped[str] = mapped_column(
        ForeignKey("audit_finding.audit_finding_id"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(nullable=False)
    engagement_criterion_id: Mapped[str] = mapped_column(
        ForeignKey("engagement_criterion.engagement_criterion_id"),
        nullable=False,
    )
    condition_statement: Mapped[str] = mapped_column(Text, nullable=False)
    cause_statement: Mapped[str] = mapped_column(Text, nullable=False)
    effect_statement: Mapped[str] = mapped_column(Text, nullable=False)
    severity_rating: Mapped[str] = mapped_column(String(16), nullable=False)
    rating_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    revised_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    revised_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RemediationAction(Base):
    """One remediation action recorded by the finding's remediation owner."""

    __tablename__ = "remediation_action"
    __table_args__ = (
        CheckConstraint(
            "(action_status = 'open' AND completed_at IS NULL "
            "AND completion_evidence_record_id IS NULL) "
            "OR (action_status = 'completed' AND completed_at IS NOT NULL "
            "AND completion_evidence_record_id IS NOT NULL)",
            name="remediation_action_completion_evidenced",
        ),
    )

    remediation_action_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_finding_id: Mapped[str] = mapped_column(
        ForeignKey("audit_finding.audit_finding_id"),
        nullable=False,
    )
    action_description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    action_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_evidence_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_record.evidence_record_id"),
        nullable=True,
    )


class FindingRetest(Base):
    """One immutable independent retest of a finding's remediation."""

    __tablename__ = "finding_retest"
    __table_args__ = (
        UniqueConstraint("audit_finding_id", "retest_number", name="finding_retest_sequence"),
        CheckConstraint("retest_number > 0", name="finding_retest_number_positive"),
        CheckConstraint(
            "retest_result IN ('passed', 'failed')",
            name="finding_retest_result_known",
        ),
    )

    finding_retest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_finding_id: Mapped[str] = mapped_column(
        ForeignKey("audit_finding.audit_finding_id"),
        nullable=False,
    )
    retest_number: Mapped[int] = mapped_column(nullable=False)
    retest_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    procedure_description: Mapped[str] = mapped_column(Text, nullable=False)
    retest_result: Mapped[str] = mapped_column(String(16), nullable=False)
    effectiveness_conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_record_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_record.evidence_record_id"),
        nullable=False,
    )
    tested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class FindingClosure(Base):
    """The single immutable closure or bounded risk-acceptance decision for a finding."""

    __tablename__ = "finding_closure"
    __table_args__ = (
        UniqueConstraint("audit_finding_id", name="finding_closure_once"),
        CheckConstraint(
            "(closure_basis = 'retest_passed' AND finding_retest_id IS NOT NULL) "
            "OR (closure_basis = 'risk_accepted' AND acceptance_authority_actor IS NOT NULL "
            "AND acceptance_expires_on IS NOT NULL)",
            name="finding_closure_basis_supported",
        ),
    )

    finding_closure_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    audit_finding_id: Mapped[str] = mapped_column(
        ForeignKey("audit_finding.audit_finding_id"),
        nullable=False,
    )
    closure_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    finding_retest_id: Mapped[str | None] = mapped_column(
        ForeignKey("finding_retest.finding_retest_id"),
        nullable=True,
    )
    closing_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    acceptance_authority_actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    acceptance_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closure_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
