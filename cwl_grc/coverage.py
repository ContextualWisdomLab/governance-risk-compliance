"""Query controls that still need evidence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cwl_grc.catalog import FrameworkCode
from cwl_grc.models import ControlEvidenceBinding, ControlItem, EvidenceRecord


def list_uncovered_controls(
    session: Session,
    framework: FrameworkCode | None,
    tenant_identifier: str | None = None,
) -> list[ControlItem]:
    """Return controls lacking evidence in the requested tenant boundary."""
    bound = select(ControlEvidenceBinding.control_item_id)
    if tenant_identifier is not None:
        bound = bound.join(
            EvidenceRecord,
            EvidenceRecord.evidence_record_id == ControlEvidenceBinding.evidence_record_id,
        ).where(EvidenceRecord.tenant_identifier == tenant_identifier)
    query = session.query(ControlItem).filter(ControlItem.control_item_id.not_in(bound))
    if framework is not None:
        query = query.filter(ControlItem.framework_key == framework.value)
    return list(query.order_by(ControlItem.framework_key, ControlItem.catalog_identifier).all())
