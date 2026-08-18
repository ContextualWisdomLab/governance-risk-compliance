"""3NF SQLAlchemy objects for the control/evidence first slice."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for GRC-owned tables."""


class ControlFramework(Base):
    """One published control catalog edition."""

    __tablename__ = "control_framework"

    framework_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    official_title: Mapped[str] = mapped_column(String(255), nullable=False)
    edition_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
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
